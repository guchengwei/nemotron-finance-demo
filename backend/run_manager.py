"""Process-local ownership and durable event delivery for Survey Runs."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import aiosqlite

from db import history_db

logger = logging.getLogger(__name__)
TERMINAL_EVENTS = {"survey_complete", "survey_error", "survey_cancelled"}
StateWriter = Callable[[aiosqlite.Connection], Awaitable[None]]


@dataclass
class Observer:
    queue: asyncio.Queue[tuple[int | None, str, dict[str, Any]]]
    dirty: bool = False


@dataclass
class RunHandle:
    run_id: str
    task: asyncio.Task[None] | None = None
    event_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    observer_state: dict[int, Observer] = field(default_factory=dict)
    cancel_requested: asyncio.Event = field(default_factory=asyncio.Event)
    completion: asyncio.Event = field(default_factory=asyncio.Event)
    terminal: bool = False

    def subscribe(self, queue_size: int = 128) -> Observer:
        observer = Observer(asyncio.Queue(maxsize=queue_size))
        self.observer_state[id(observer)] = observer
        return observer

    def unsubscribe(self, observer: Observer) -> None:
        self.observer_state.pop(id(observer), None)

    def publish(self, seq: int | None, event_type: str, data: dict[str, Any]) -> None:
        for observer in tuple(self.observer_state.values()):
            try:
                observer.queue.put_nowait((seq, event_type, data))
            except asyncio.QueueFull:
                if seq is not None:
                    observer.dirty = True


class RunManager:
    def __init__(self) -> None:
        self.handles: dict[str, RunHandle] = {}

    def get_or_create(self, run_id: str) -> RunHandle:
        return self.handles.setdefault(run_id, RunHandle(run_id))

    def start(self, run_id: str, runner: Callable[[RunHandle], Awaitable[None]]) -> RunHandle:
        handle = self.get_or_create(run_id)
        if handle.task is None or handle.task.done():
            handle.task = asyncio.create_task(runner(handle), name=f"survey-run:{run_id}")
        return handle

    async def append_event(
        self,
        handle: RunHandle,
        event_type: str,
        data: dict[str, Any],
        state_writer: StateWriter | None = None,
    ) -> int | None:
        async with handle.event_lock:
            if handle.terminal:
                return None
            async with history_db() as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    if state_writer is not None:
                        await state_writer(db)
                    rows = await db.execute_fetchall(
                        "SELECT COALESCE(MAX(seq), 0) + 1 FROM run_events WHERE run_id = ?",
                        [handle.run_id],
                    )
                    seq = int(rows[0][0])
                    await db.execute(
                        "INSERT INTO run_events (run_id, seq, event_type, data_json) VALUES (?, ?, ?, ?)",
                        [handle.run_id, seq, event_type, json.dumps(data, ensure_ascii=False)],
                    )
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise
            if event_type in TERMINAL_EVENTS:
                handle.terminal = True
                handle.completion.set()
            handle.publish(seq, event_type, data)
            return seq

    def publish_delta(self, handle: RunHandle, event_type: str, data: dict[str, Any]) -> None:
        if not handle.terminal:
            handle.publish(None, event_type, data)

    async def cancel(self, run_id: str) -> str | None:
        async with history_db() as db:
            rows = await db.execute_fetchall("SELECT status FROM survey_runs WHERE id = ?", [run_id])
        if not rows:
            return None
        status = str(rows[0][0])
        if status == "running":
            handle = self.get_or_create(run_id)
            handle.cancel_requested.set()
            if handle.task and not handle.task.done():
                handle.task.cancel()
        return status

    async def shutdown(self) -> None:
        active: list[RunHandle] = []
        tasks: list[asyncio.Task[None]] = []
        for handle in self.handles.values():
            if handle.task and not handle.task.done():
                handle.task.cancel()
                tasks.append(handle.task)
                active.append(handle)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for handle in active:
            if handle.terminal:
                continue
            async with history_db() as db:
                run_rows = await db.execute_fetchall(
                    "SELECT persona_count, status FROM survey_runs WHERE id = ?", [handle.run_id]
                )
                outcome_rows = await db.execute_fetchall(
                    "SELECT event_type, COUNT(*) FROM run_events WHERE run_id = ? "
                    "AND event_type IN ('persona_complete', 'persona_error') "
                    "GROUP BY event_type", [handle.run_id]
                )
            if not run_rows or run_rows[0][1] != "running":
                continue
            counts = dict(outcome_rows)
            total = int(run_rows[0][0] or 0)
            completed = int(counts.get("persona_complete", 0))
            # Only persona-scoped errors count here; derive exactly below.
            async with history_db() as db:
                error_rows = await db.execute_fetchall(
                    "SELECT data_json FROM run_events WHERE run_id = ? AND event_type = 'persona_error'",
                    [handle.run_id],
                )
            failed = sum(json.loads(row[0]).get("scope") == "persona" for row in error_rows)
            payload = terminal_payload(handle.run_id, total, completed, failed, "server_shutdown")

            async def fail(db: aiosqlite.Connection, rid=handle.run_id) -> None:
                await db.execute("UPDATE survey_runs SET status = 'failed' WHERE id = ? AND status = 'running'", [rid])

            await self.append_event(handle, "survey_error", payload, fail)

    async def reconcile_orphans(self, code: str = "server_restart") -> None:
        async with history_db() as db:
            rows = await db.execute_fetchall("SELECT id, persona_count FROM survey_runs WHERE status = 'running'")
        for run_id, total in rows:
            handle = self.get_or_create(str(run_id))
            payload = terminal_payload(str(run_id), int(total or 0), 0, 0, code=code)

            async def fail(db: aiosqlite.Connection, rid=str(run_id)) -> None:
                await db.execute("UPDATE survey_runs SET status = 'failed' WHERE id = ? AND status = 'running'", [rid])

            await self.append_event(handle, "survey_error", payload, fail)


def public_error(code: str, scope: str | None = None, **identifiers: Any) -> dict[str, Any]:
    messages = {
        "llm_unreachable": "回答サービスに接続できませんでした。",
        "generation_timeout": "回答の生成がタイムアウトしました。",
        "server_restart": "サーバーの再起動により実行を継続できませんでした。",
        "server_shutdown": "サーバー停止により実行を完了できませんでした。",
        "run_cancelled": "アンケート実行はキャンセルされました。",
        "internal_error": "処理中にエラーが発生しました。",
    }
    result: dict[str, Any] = {
        "code": code,
        "message": messages.get(code, messages["internal_error"]),
        "retryable": code in {"llm_unreachable", "generation_timeout"},
        "correlation_id": str(uuid.uuid4()),
        **identifiers,
    }
    if scope:
        result["scope"] = scope
    return result


def terminal_payload(run_id: str, total: int, completed: int, failed: int, code: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "total": total,
        "completed": completed,
        "failed": failed,
        "not_completed": max(0, total - completed - failed),
    }
    if code:
        payload.update(public_error(code, run_id=run_id))
    return payload


run_manager = RunManager()
