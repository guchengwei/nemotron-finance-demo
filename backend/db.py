"""Deprecated SQLite-backed history store helpers.

Persona data no longer lives in SQLite. Personas are loaded from parquet into
the pandas-backed `persona_store.py`. This module remains only for persisted
survey history and follow-up chat state.
"""

import re
import os
import sqlite3
import logging
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
    enable_thinking BOOLEAN DEFAULT 1
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
"""


def _create_history_db():
    os.makedirs(os.path.dirname(settings.history_db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.history_db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(HISTORY_DDL)
    # Migrate: add enable_thinking if missing
    try:
        conn.execute("ALTER TABLE survey_runs ADD COLUMN enable_thinking BOOLEAN DEFAULT 1")
        conn.commit()
        logger.info("Migrated survey_runs: added enable_thinking column")
    except Exception:
        pass  # Column already exists
    # Fix any surveys stuck in 'running' status from previous crashes
    stuck = conn.execute(
        "UPDATE survey_runs SET status = 'failed' WHERE status = 'running'"
    ).rowcount
    conn.commit()
    if stuck:
        logger.info("Cleaned up %d stuck 'running' survey(s)", stuck)
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


async def get_history_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(settings.history_db_path)
