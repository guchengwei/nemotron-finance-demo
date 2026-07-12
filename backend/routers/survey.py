"""Durable, resumable Survey Run HTTP contract."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import Any, AsyncGenerator

import aiosqlite
from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from config import settings
from db import history_db
from e2e_support import get_e2e_scenario
from llm import generate_questions, sanitize_answer_text, stream_survey_answer
from models import QuestionGenerationRequest, QuestionGenerationResponse, SurveyRunRequest
from prompts import build_survey_system_prompt, sex_display
from run_manager import RunHandle, TERMINAL_EVENTS, public_error, run_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/survey", tags=["survey"])
_SCORE_RE_1 = re.compile(r"【評価[:：]\s*(\d)】")
_SCORE_RE_2 = re.compile(r"^(\d)\s*[。、.:/／]")


def extract_score(text: str) -> int | None:
    match = _SCORE_RE_1.search(text) or _SCORE_RE_2.match(text.strip())
    return int(match.group(1)) if match else None


def _persona_summary(persona: dict[str, Any]) -> str:
    return (
        f"{persona.get('name', '不明')}, {persona.get('age', '?')}歳"
        f"{sex_display(persona.get('sex', ''))}, {persona.get('occupation', '')}, "
        f"{persona.get('prefecture', '')}"
    )


def _snapshot_personas(persona_ids: list[str]) -> list[dict[str, Any]]:
    from persona_store import get_store

    store = get_store()
    snapshots = []
    for position, persona_id in enumerate(persona_ids):
        persona = store.get_persona(persona_id)
        if not persona:
            raise HTTPException(status_code=422, detail=f"Unknown persona: {persona_id}")
        financial = store.get_cached_financial(persona_id)
        if financial:
            persona = {**persona, "financial_extension": financial}
        snapshots.append(
            {
                "persona_uuid": persona_id,
                "position": position,
                "persona_summary": _persona_summary(persona),
                "persona_full_json": json.dumps(persona, ensure_ascii=False, default=str),
            }
        )
    return snapshots


def _fingerprint(request: SurveyRunRequest) -> str:
    canonical = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _run_persona(
    handle: RunHandle,
    snapshot: dict[str, Any],
    questions: list[str],
    theme: str,
    total_personas: int,
    enable_thinking: bool,
    semaphore: asyncio.Semaphore,
    result_queue: asyncio.Queue[str],
    e2e_scenario: str | None,
) -> None:
    persona_id = snapshot["persona_uuid"]
    position = snapshot["position"]
    persona = json.loads(snapshot["persona_full_json"])
    persona_failed = False
    try:
        async with semaphore:
            await run_manager.append_event(
                handle,
                "persona_start",
                {"persona_uuid": persona_id, "name": persona.get("name", "不明"), "index": position, "total": total_personas},
            )
            system_prompt = build_survey_system_prompt(persona, persona.get("financial_extension"))
            for question_index, question in enumerate(questions):
                if handle.cancel_requested.is_set():
                    raise asyncio.CancelledError
                answer = ""
                thinking = ""
                try:
                    async for kind, chunk in stream_survey_answer(
                        persona, system_prompt, question, question_index, enable_thinking=enable_thinking
                    ):
                        if kind == "think":
                            thinking = chunk
                        else:
                            cleaned = sanitize_answer_text(chunk)
                            answer += cleaned
                            run_manager.publish_delta(
                                handle,
                                "persona_answer_chunk",
                                {"persona_uuid": persona_id, "question_index": question_index, "chunk": cleaned},
                            )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    error = public_error(
                        "llm_unreachable", "question", run_id=handle.run_id,
                        persona_uuid=persona_id, question_index=question_index,
                    )
                    logger.exception("Question generation failed correlation_id=%s", error["correlation_id"])

                    async def save_failure(db: aiosqlite.Connection) -> None:
                        await db.execute(
                            "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary, persona_full_json, "
                            "question_index, question_text, answer, outcome, error_code, error_message, correlation_id) "
                            "VALUES (?, ?, ?, ?, ?, ?, NULL, 'failed', ?, ?, ?)",
                            [handle.run_id, persona_id, snapshot["persona_summary"], snapshot["persona_full_json"],
                             question_index, question, error["code"], error["message"], error["correlation_id"]],
                        )

                    await run_manager.append_event(handle, "persona_error", error, save_failure)
                    continue

                answer = sanitize_answer_text(answer)
                score = extract_score(answer)
                payload = {
                    "persona_uuid": persona_id, "question_index": question_index,
                    "answer": answer, "score": score, "thinking": thinking or None,
                }

                async def save_answer(db: aiosqlite.Connection) -> None:
                    await db.execute(
                        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary, persona_full_json, "
                        "question_index, question_text, answer, score, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'answered')",
                        [handle.run_id, persona_id, snapshot["persona_summary"], snapshot["persona_full_json"],
                         question_index, question, answer, score],
                    )

                await run_manager.append_event(handle, "persona_answer", payload, save_answer)
                if e2e_scenario == "survey_fail_mid_run" and position == 0 and question_index == 0:
                    raise RuntimeError("forced E2E interruption")
            await run_manager.append_event(
                handle, "persona_complete", {"persona_uuid": persona_id, "index": position}
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        persona_failed = True
        error = public_error("internal_error", "persona", run_id=handle.run_id, persona_uuid=persona_id)
        logger.exception("Persona execution failed correlation_id=%s", error["correlation_id"])
        await run_manager.append_event(handle, "persona_error", error)
    finally:
        await result_queue.put("failed" if persona_failed else "completed")


async def _execute_run(handle: RunHandle, e2e_scenario: str | None = None) -> None:
    async with history_db() as db:
        db.row_factory = aiosqlite.Row
        run_rows = await db.execute_fetchall("SELECT * FROM survey_runs WHERE id = ?", [handle.run_id])
        snapshot_rows = await db.execute_fetchall(
            "SELECT * FROM run_personas WHERE run_id = ? ORDER BY position", [handle.run_id]
        )
    if not run_rows:
        return
    run = dict(run_rows[0])
    snapshots = [dict(row) for row in snapshot_rows]
    tasks: list[asyncio.Task[None]] = []
    try:
        questions = json.loads(run["questions_json"] or "[]")
        if not questions:
            questions = await generate_questions(run["survey_theme"], enable_thinking=bool(run["enable_thinking"]))

            async def save_questions(db: aiosqlite.Connection) -> None:
                await db.execute(
                    "UPDATE survey_runs SET questions_json = ? WHERE id = ?",
                    [json.dumps(questions, ensure_ascii=False), handle.run_id],
                )

            await run_manager.append_event(handle, "questions_generated", {"questions": questions}, save_questions)
        else:
            await run_manager.append_event(handle, "questions_generated", {"questions": questions})

        results: asyncio.Queue[str] = asyncio.Queue(maxsize=len(snapshots))
        semaphore = asyncio.Semaphore(settings.llm_concurrency)
        tasks = [
            asyncio.create_task(_run_persona(handle, snapshot, questions, run["survey_theme"], len(snapshots),
                                             bool(run["enable_thinking"]), semaphore, results, e2e_scenario))
            for snapshot in snapshots
        ]
        for _ in snapshots:
            await results.get()
        await asyncio.gather(*tasks)
        await run_manager.finish_run(handle, "survey_complete", "completed", len(snapshots))
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if handle.cancel_requested.is_set():
            await run_manager.finish_run(
                handle, "survey_cancelled", "cancelled", len(snapshots),
                "run_cancelled", "run_cancelled",
            )
        else:
            raise
    except Exception:
        logger.exception("Survey Run failed run_id=%s", handle.run_id)
        await run_manager.finish_run(
            handle, "survey_error", "failed", len(snapshots), "internal_error", "run_failed"
        )


@router.post("/questions", response_model=QuestionGenerationResponse)
async def create_questions(request: QuestionGenerationRequest):
    questions = await generate_questions(request.survey_theme, enable_thinking=request.enable_thinking is not False)
    return QuestionGenerationResponse(questions=questions)


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_survey(
    request: SurveyRunRequest,
    http_request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
):
    fingerprint = _fingerprint(request)
    async with history_db() as db:
        db.row_factory = aiosqlite.Row
        existing = await db.execute_fetchall(
            "SELECT id, request_fingerprint, status FROM survey_runs WHERE idempotency_key = ?", [idempotency_key]
        )
        if existing:
            row = existing[0]
            if row["request_fingerprint"] != fingerprint:
                raise HTTPException(status_code=409, detail="Idempotency-Key was used for a different request")
            run_id = str(row["id"])
            if row["status"] == "running":
                run_manager.start(run_id, lambda handle: _execute_run(handle, get_e2e_scenario(http_request)))
            return {"run_id": run_id, "status": row["status"]}

        snapshots = _snapshot_personas(request.persona_ids)
        run_id = str(uuid.uuid4())
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                "INSERT INTO survey_runs (id, survey_theme, questions_json, persona_count, status, label, "
                "enable_thinking, idempotency_key, request_fingerprint) VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)",
                [run_id, request.survey_theme, json.dumps(request.questions or [], ensure_ascii=False),
                 len(snapshots), request.label, request.enable_thinking is not False, idempotency_key, fingerprint],
            )
            for snapshot in snapshots:
                await db.execute(
                    "INSERT INTO run_personas (run_id, persona_uuid, position, persona_summary, persona_full_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [run_id, snapshot["persona_uuid"], snapshot["position"], snapshot["persona_summary"], snapshot["persona_full_json"]],
                )
            payload = {"run_id": run_id, "total_personas": len(snapshots)}
            await db.execute(
                "INSERT INTO run_events (run_id, seq, event_type, data_json) VALUES (?, 1, 'run_created', ?)",
                [run_id, json.dumps(payload, ensure_ascii=False)],
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            await db.rollback()
            raced = await db.execute_fetchall(
                "SELECT id, request_fingerprint, status FROM survey_runs WHERE idempotency_key = ?",
                [idempotency_key],
            )
            if not raced or raced[0]["request_fingerprint"] != fingerprint:
                raise HTTPException(status_code=409, detail="Idempotency-Key was used for a different request")
            raced_run_id = str(raced[0]["id"])
            if raced[0]["status"] == "running":
                run_manager.start(raced_run_id, lambda active_handle: _execute_run(active_handle, get_e2e_scenario(http_request)))
            return {"run_id": raced_run_id, "status": raced[0]["status"]}
        except BaseException:
            await db.rollback()
            raise
    handle = run_manager.get_or_create(run_id)
    handle.publish(1, "run_created", payload)
    run_manager.start(run_id, lambda active_handle: _execute_run(active_handle, get_e2e_scenario(http_request)))
    return {"run_id": run_id, "status": "running"}


def _frame(seq: int | None, event_type: str, data: dict[str, Any]) -> str:
    prefix = f"id: {seq}\n" if seq is not None else ""
    return f"{prefix}event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _observe(run_id: str, cursor: int) -> AsyncGenerator[str, None]:
    handle = run_manager.get_or_create(run_id)
    observer = handle.subscribe()
    try:
        while True:
            async with history_db() as db:
                rows = await db.execute_fetchall(
                    "SELECT seq, event_type, data_json FROM run_events WHERE run_id = ? AND seq > ? ORDER BY seq",
                    [run_id, cursor],
                )
            for seq, event_type, data_json in rows:
                cursor = int(seq)
                yield _frame(cursor, str(event_type), json.loads(data_json))
                if event_type in TERMINAL_EVENTS:
                    return
            observer.dirty = False
            try:
                seq, event_type, data = await asyncio.wait_for(observer.queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if seq is not None and seq <= cursor:
                continue
            if observer.dirty and seq is not None:
                continue
            if seq is not None:
                cursor = seq
            yield _frame(seq, event_type, data)
            if event_type in TERMINAL_EVENTS:
                return
    finally:
        handle.unsubscribe(observer)


@router.get("/stream/{run_id}")
async def stream_run(
    run_id: str,
    last_event_id_query: int | None = Query(None, alias="last_event_id", ge=0),
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
):
    try:
        cursor = last_event_id_query if last_event_id_query is not None else int(last_event_id_header or 0)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid Last-Event-ID") from error
    async with history_db() as db:
        rows = await db.execute_fetchall(
            "SELECT status, EXISTS(SELECT 1 FROM run_events WHERE run_id = ?) FROM survey_runs WHERE id = ?",
            [run_id, run_id],
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Run not found")
    if not rows[0][1]:
        raise HTTPException(status_code=409, detail=public_error("replay_unavailable", run_id=run_id))
    return StreamingResponse(_observe(run_id, cursor), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(run_id: str):
    outcome = await run_manager.cancel(run_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if outcome in {"completed", "failed"}:
        raise HTTPException(status_code=409, detail={"status": outcome})
    return {"run_id": run_id, "status": "cancellation_pending" if outcome == "running" else outcome}
