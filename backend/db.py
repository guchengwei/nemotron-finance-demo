"""Deprecated SQLite-backed history store helpers.

Persona data no longer lives in SQLite. Personas are loaded from parquet into
the pandas-backed `persona_store.py`. This module remains only for persisted
survey history and follow-up chat state.
"""

import re
import os
import sqlite3
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

# -- Name extraction ----------------------------------------------------------

_NAME_PATTERN_1 = re.compile(r'^([^\s]{1,4})\s([^\s]{1,5})[はの]')
_NAME_PATTERN_2 = re.compile(r'^(.+?)は[、,]')


def extract_name(persona_text: str) -> str:
    """Extract Japanese name from start of persona text."""
    if not persona_text:
        return "不明"
    m = _NAME_PATTERN_1.match(persona_text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = _NAME_PATTERN_2.match(persona_text)
    if m and len(m.group(1)) <= 10:
        return m.group(1)
    return "不明"


# -- Schema creation ----------------------------------------------------------

HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS survey_runs (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    survey_theme TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    filter_config_json TEXT,
    persona_count INTEGER,
    status TEXT DEFAULT 'running',
    report_json TEXT,
    label TEXT,
    enable_thinking BOOLEAN DEFAULT 1,
    idempotency_key TEXT,
    request_fingerprint TEXT
);

CREATE TABLE IF NOT EXISTS survey_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES survey_runs(id),
    persona_uuid TEXT,
    persona_summary TEXT,
    persona_full_json TEXT,
    question_index INTEGER,
    question_text TEXT,
    answer TEXT,
    score INTEGER,
    outcome TEXT NOT NULL DEFAULT 'answered',
    error_code TEXT,
    error_message TEXT,
    correlation_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_personas (
    run_id TEXT NOT NULL REFERENCES survey_runs(id) ON DELETE CASCADE,
    persona_uuid TEXT NOT NULL,
    position INTEGER NOT NULL,
    persona_summary TEXT NOT NULL,
    persona_full_json TEXT NOT NULL,
    PRIMARY KEY (run_id, persona_uuid),
    UNIQUE (run_id, position)
);

CREATE TABLE IF NOT EXISTS run_events (
    run_id TEXT NOT NULL REFERENCES survey_runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS followup_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES survey_runs(id),
    persona_uuid TEXT,
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_answers_run ON survey_answers(run_id);
CREATE INDEX IF NOT EXISTS idx_followup_run ON followup_chats(run_id, persona_uuid);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, seq);
"""


_ADDITIVE_COLUMNS = {
    "survey_runs": (
        ("enable_thinking", "BOOLEAN DEFAULT 1"),
        ("matrix_report_json", "TEXT"),
        ("idempotency_key", "TEXT"),
        ("request_fingerprint", "TEXT"),
    ),
    "survey_answers": (
        ("outcome", "TEXT NOT NULL DEFAULT 'answered'"),
        ("error_code", "TEXT"),
        ("error_message", "TEXT"),
        ("correlation_id", "TEXT"),
    ),
}

_HISTORY_PRAGMAS = (
    "PRAGMA foreign_keys=ON",
    f"PRAGMA busy_timeout={settings.history_db_busy_timeout_ms}",
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
)


def _configure_sync_connection(connection: sqlite3.Connection) -> None:
    for pragma in _HISTORY_PRAGMAS:
        connection.execute(pragma)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Apply additive upgrades while leaving every existing row intact."""
    for table, columns in _ADDITIVE_COLUMNS.items():
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, declaration in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
                logger.info("Migrated %s: added %s column", table, name)

    # SQLite cannot add a UNIQUE column with ALTER TABLE. A partial index gives
    # upgraded databases the same idempotency guarantee while allowing legacy
    # NULL values.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_survey_runs_idempotency_key "
        "ON survey_runs(idempotency_key) WHERE idempotency_key IS NOT NULL"
    )


def _create_history_db():
    os.makedirs(os.path.dirname(settings.history_db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(
        settings.history_db_path,
        timeout=settings.history_db_busy_timeout_ms / 1000,
    )
    _configure_sync_connection(conn)
    conn.executescript(HISTORY_DDL)
    _add_missing_columns(conn)
    conn.commit()
    conn.close()
    logger.info("History DB ready: %s", settings.history_db_path)


def _download_dataset(parquet_path: Path):
    """Download dataset from HuggingFace and save as parquet."""
    from datasets import load_dataset
    logger.info("Downloading nvidia/Nemotron-Personas-Japan from HuggingFace (~1.7GB)...")
    ds = load_dataset(settings.persona_hf_dataset, split="train")
    logger.info("Downloaded. Columns: %s, Rows: %d", ds.column_names, len(ds))
    os.makedirs(parquet_path.parent, exist_ok=True)
    ds.to_parquet(str(parquet_path))
    logger.info("Saved to %s", parquet_path)


def get_history_db_sync(db_path: str | None = None) -> sqlite3.Connection:
    """Open one consistently configured synchronous history connection."""
    connection = sqlite3.connect(
        db_path or settings.history_db_path,
        timeout=settings.history_db_busy_timeout_ms / 1000,
    )
    _configure_sync_connection(connection)
    return connection


async def get_history_db() -> aiosqlite.Connection:
    """Open one consistently configured async history connection."""
    connection = await aiosqlite.connect(
        settings.history_db_path,
        timeout=settings.history_db_busy_timeout_ms / 1000,
    )
    try:
        for pragma in _HISTORY_PRAGMAS:
            await connection.execute(pragma)
    except BaseException:
        await connection.close()
        raise
    return connection


@asynccontextmanager
async def history_db():
    """Context-managed access to the configured history database."""
    connection = await get_history_db()
    try:
        yield connection
    finally:
        await connection.close()
