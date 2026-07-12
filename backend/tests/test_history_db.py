import asyncio
import sqlite3

import pytest

from config import settings
from db import _create_history_db, get_history_db


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
