import asyncio
import json
import sqlite3

import pytest
import aiosqlite
from unittest.mock import patch

from config import settings
from db import _create_history_db, get_history_db
from run_manager import RunManager, run_manager
from routers.survey import _observe


@pytest.fixture
def history_path(tmp_path):
    original = settings.history_db_path
    settings.history_db_path = str(tmp_path / "history.db")
    try:
        yield settings.history_db_path
    finally:
        settings.history_db_path = original


def test_fresh_history_database_has_durable_run_storage(history_path):
    _create_history_db()

    with sqlite3.connect(history_path) as connection:
        run_columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(survey_runs)")
        }
        answer_columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(survey_answers)")
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"idempotency_key", "request_fingerprint"} <= run_columns.keys()
    assert {"outcome", "error_code", "error_message", "correlation_id"} <= answer_columns.keys()
    assert answer_columns["outcome"][3] == 1
    assert answer_columns["outcome"][4] == "'answered'"
    assert {"run_personas", "run_events"} <= tables


def test_version_one_database_upgrades_without_changing_history(history_path):
    with sqlite3.connect(history_path) as connection:
        connection.executescript(
            """
            CREATE TABLE survey_runs (
                id TEXT PRIMARY KEY,
                survey_theme TEXT NOT NULL,
                questions_json TEXT NOT NULL,
                status TEXT DEFAULT 'running'
            );
            CREATE TABLE survey_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT REFERENCES survey_runs(id),
                persona_uuid TEXT,
                answer TEXT
            );
            INSERT INTO survey_runs (id, survey_theme, questions_json, status)
            VALUES ('legacy', 'theme', '["question"]', 'completed');
            INSERT INTO survey_answers (run_id, persona_uuid, answer)
            VALUES ('legacy', 'persona', 'answer');
            """
        )

    _create_history_db()

    with sqlite3.connect(history_path) as connection:
        answer = connection.execute(
            "SELECT answer, outcome FROM survey_answers WHERE run_id = 'legacy'"
        ).fetchone()
        run = connection.execute(
            "SELECT status FROM survey_runs WHERE id = 'legacy'"
        ).fetchone()
        snapshot_count = connection.execute("SELECT count(*) FROM run_personas").fetchone()[0]
        event_count = connection.execute("SELECT count(*) FROM run_events").fetchone()[0]

    assert answer == ("answer", "answered")
    assert run == ("completed",)
    assert snapshot_count == 0
    assert event_count == 0


def test_configured_connections_enable_sqlite_safety_policy(history_path):
    _create_history_db()

    async def inspect_policy():
        connection = await get_history_db()
        try:
            foreign_keys = (await (await connection.execute("PRAGMA foreign_keys")).fetchone())[0]
            journal_mode = (await (await connection.execute("PRAGMA journal_mode")).fetchone())[0]
            busy_timeout = (await (await connection.execute("PRAGMA busy_timeout")).fetchone())[0]
            return foreign_keys, journal_mode, busy_timeout
        finally:
            await connection.close()

    foreign_keys, journal_mode, busy_timeout = asyncio.run(inspect_policy())

    assert foreign_keys == 1
    assert journal_mode.lower() == "wal"
    assert busy_timeout == 30_000


def test_configured_connections_tolerate_concurrent_read_and_write(history_path):
    _create_history_db()

    async def exercise_connections():
        writer = await get_history_db()
        reader = await get_history_db()
        try:
            await writer.execute("BEGIN IMMEDIATE")
            await writer.execute(
                "INSERT INTO survey_runs (id, survey_theme, questions_json) VALUES (?, ?, ?)",
                ("concurrent", "theme", "[]"),
            )
            read_task = asyncio.create_task(
                reader.execute_fetchall("SELECT id FROM survey_runs")
            )
            assert await asyncio.wait_for(read_task, timeout=1) == []
            await writer.commit()
            assert await reader.execute_fetchall(
                "SELECT id FROM survey_runs WHERE id = ?", ("concurrent",)
            )
        finally:
            await writer.close()
            await reader.close()

    asyncio.run(exercise_connections())


def test_state_and_event_roll_back_together_on_persistence_failure(history_path):
    _create_history_db()
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json) VALUES ('atomic', 'theme', '[]')"
        )
        connection.commit()

    manager = RunManager()
    handle = manager.get_or_create("atomic")

    async def exercise_failure():
        async def broken_writer(connection):
            await connection.execute(
                "INSERT INTO survey_answers (run_id, persona_uuid, question_index, outcome) "
                "VALUES ('atomic', 'p1', 0, 'answered')"
            )
            raise RuntimeError("injected persistence failure")

        with pytest.raises(RuntimeError, match="injected"):
            await manager.append_event(handle, "persona_answer", {"answer": "hidden"}, broken_writer)

    asyncio.run(exercise_failure())
    with sqlite3.connect(history_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM survey_answers WHERE run_id = 'atomic'").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_events WHERE run_id = 'atomic'").fetchone()[0] == 0


def test_terminal_status_rolls_back_when_event_insert_fails(history_path):
    _create_history_db()
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, status) "
            "VALUES ('terminal-atomic', 'theme', '[]', 'running')"
        )
        connection.commit()
    manager = RunManager()
    handle = manager.get_or_create("terminal-atomic")
    original_execute = aiosqlite.Connection.execute

    async def fail_event_insert(connection, sql, *args, **kwargs):
        if "INSERT INTO run_events" in sql:
            raise sqlite3.OperationalError("injected event failure")
        return await original_execute(connection, sql, *args, **kwargs)

    async def exercise():
        with patch.object(aiosqlite.Connection, "execute", new=fail_event_insert):
            with pytest.raises(sqlite3.OperationalError, match="injected"):
                await manager.finish_run(handle, "survey_complete", "completed", 0)

    asyncio.run(exercise())
    with sqlite3.connect(history_path) as connection:
        assert connection.execute(
            "SELECT status FROM survey_runs WHERE id = 'terminal-atomic'"
        ).fetchone()[0] == "running"
        assert connection.execute(
            "SELECT COUNT(*) FROM run_events WHERE run_id = 'terminal-atomic'"
        ).fetchone()[0] == 0


def test_startup_reconciliation_creates_one_safe_terminal_event(history_path):
    _create_history_db()
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, persona_count, status) "
            "VALUES ('orphan', 'theme', '[]', 2, 'running')"
        )
        connection.execute(
            "INSERT INTO run_events (run_id, seq, event_type, data_json) "
            "VALUES ('orphan', 1, 'persona_complete', '{\"persona_uuid\": \"p1\"}')"
        )
        connection.commit()

    asyncio.run(run_manager.reconcile_orphans())
    asyncio.run(run_manager.reconcile_orphans())

    with sqlite3.connect(history_path) as connection:
        status = connection.execute("SELECT status FROM survey_runs WHERE id = 'orphan'").fetchone()[0]
        events = connection.execute(
            "SELECT seq, event_type, data_json FROM run_events WHERE run_id = 'orphan'"
        ).fetchall()
    assert status == "failed"
    assert len(events) == 2
    assert events[-1][:2] == (2, "survey_error")
    payload = json.loads(events[-1][2])
    assert payload["code"] == "server_restart"
    assert payload["completed"] == 1
    assert payload["not_completed_reason"] == "run_failed"
    assert payload["completed"] + payload["failed"] + payload["not_completed"] == payload["total"]


def test_slow_observer_marks_gap_and_durable_log_recovers_every_sequence(history_path):
    _create_history_db()
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json) VALUES ('overflow', 'theme', '[]')"
        )
        connection.commit()
    manager = RunManager()
    handle = manager.get_or_create("overflow")
    observer = handle.subscribe(queue_size=1)

    async def append_events():
        for index in range(3):
            await manager.append_event(handle, "persona_start", {"index": index})

    asyncio.run(append_events())
    assert observer.dirty is True
    with sqlite3.connect(history_path) as connection:
        recovered = connection.execute(
            "SELECT seq FROM run_events WHERE run_id = 'overflow' AND seq > 0 ORDER BY seq"
        ).fetchall()
    assert recovered == [(1,), (2,), (3,)]


def test_two_concurrent_observers_receive_identical_persisted_sequences(history_path):
    _create_history_db()
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, persona_count) "
            "VALUES ('observed', 'theme', '[]', 0)"
        )
        connection.commit()
    handle = run_manager.get_or_create("observed")

    async def exercise():
        async def collect():
            frames = []
            async for frame in _observe("observed", 0):
                frames.append(frame)
            return frames

        observers = [asyncio.create_task(collect()), asyncio.create_task(collect())]
        await asyncio.sleep(0)
        await run_manager.append_event(handle, "run_created", {"run_id": "observed"})
        await run_manager.finish_run(handle, "survey_complete", "completed", 0)
        return await asyncio.gather(*observers)

    first, second = asyncio.run(exercise())
    first_ids = [int(line[4:]) for frame in first for line in frame.splitlines() if line.startswith("id: ")]
    second_ids = [int(line[4:]) for frame in second for line in frame.splitlines() if line.startswith("id: ")]
    assert first_ids == second_ids == [1, 2]


def test_completion_and_cancellation_race_reserves_exactly_one_terminal_event(history_path):
    _create_history_db()
    with sqlite3.connect(history_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, persona_count) "
            "VALUES ('race', 'theme', '[]', 0)"
        )
        connection.commit()
    manager = RunManager()
    handle = manager.get_or_create("race")

    async def race():
        await asyncio.gather(
            manager.finish_run(handle, "survey_complete", "completed", 0),
            manager.cancel("race"),
        )

    asyncio.run(race())
    with sqlite3.connect(history_path) as connection:
        status = connection.execute("SELECT status FROM survey_runs WHERE id = 'race'").fetchone()[0]
        terminals = connection.execute(
            "SELECT event_type FROM run_events WHERE run_id = 'race' "
            "AND event_type IN ('survey_complete', 'survey_cancelled', 'survey_error')"
        ).fetchall()
    assert len(terminals) == 1
    assert (status, terminals[0][0]) in {
        ("completed", "survey_complete"), ("cancelled", "survey_cancelled")
    }
