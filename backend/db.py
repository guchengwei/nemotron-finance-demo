"""SQLite database initialization and access.

Loads personas from HuggingFace parquet into SQLite at startup.
V3 schema: 23 columns, name extracted from persona text via regex.
Sex values: 男/女
"""

import re
import os
import sqlite3
import logging
import asyncio
from pathlib import Path
from typing import Optional

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


# -- Persona DB ---------------------------------------------------------------

def _get_persona_conn():
    return sqlite3.connect(settings.db_path, timeout=30)


def _get_history_conn():
    return sqlite3.connect(settings.history_db_path, timeout=30)


async def get_persona_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(settings.db_path)


async def get_history_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(settings.history_db_path)


# -- Schema creation ----------------------------------------------------------

PERSONA_DDL = """
CREATE TABLE IF NOT EXISTS personas (
    uuid TEXT PRIMARY KEY,
    name TEXT,
    professional_persona TEXT,
    sports_persona TEXT,
    arts_persona TEXT,
    travel_persona TEXT,
    culinary_persona TEXT,
    persona TEXT,
    cultural_background TEXT,
    skills_and_expertise TEXT,
    skills_and_expertise_list TEXT,
    hobbies_and_interests TEXT,
    hobbies_and_interests_list TEXT,
    career_goals_and_ambitions TEXT,
    sex TEXT,
    age INTEGER,
    marital_status TEXT,
    education_level TEXT,
    occupation TEXT,
    region TEXT,
    area TEXT,
    prefecture TEXT,
    country TEXT
);
CREATE INDEX IF NOT EXISTS idx_sex ON personas(sex);
CREATE INDEX IF NOT EXISTS idx_age ON personas(age);
CREATE INDEX IF NOT EXISTS idx_prefecture ON personas(prefecture);
CREATE INDEX IF NOT EXISTS idx_region ON personas(region);
CREATE INDEX IF NOT EXISTS idx_occupation ON personas(occupation);
CREATE INDEX IF NOT EXISTS idx_education ON personas(education_level);
"""

FINANCIAL_EXT_DDL = """
CREATE TABLE IF NOT EXISTS persona_financial_context (
    persona_uuid TEXT PRIMARY KEY,
    financial_literacy TEXT,
    investment_experience TEXT,
    financial_concerns TEXT,
    annual_income_bracket TEXT,
    asset_bracket TEXT,
    primary_bank_type TEXT
);
"""

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
    label TEXT
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
    conn.executescript(HISTORY_DDL)
    conn.commit()
    conn.close()
    logger.info("History DB ready: %s", settings.history_db_path)


def _load_personas_to_sqlite():
    """Load parquet → SQLite. Skips if DB already has correct row count."""
    raw_parquet = (settings.persona_parquet_path or "").strip()
    if raw_parquet:
        parquet_path = Path(raw_parquet).expanduser()
    else:
        parquet_path = Path(settings.data_dir) / "personas.parquet"

    if str(parquet_path) in (".", "./", ""):
        raise RuntimeError(
            "PERSONA_PARQUET_PATH resolves to current directory. "
            "Set it to a .parquet file path or leave blank for auto-download."
        )

    db_path = Path(settings.db_path)

    os.makedirs(db_path.parent, exist_ok=True)

    # Check if DB already loaded
    if db_path.exists():
        conn = sqlite3.connect(str(db_path), timeout=30)
        try:
            row = conn.execute("SELECT COUNT(*) FROM personas").fetchone()
            existing_count = row[0] if row else 0
            conn.close()
            if existing_count > 0:
                logger.info("Persona DB already loaded: %d rows — skipping reload", existing_count)
                _ensure_financial_ext_table()
                return
        except Exception:
            conn.close()

    # Load from parquet
    if not parquet_path.exists():
        logger.info("Parquet not found locally — downloading from HuggingFace...")
        _download_dataset(parquet_path)

    logger.info("Loading parquet into SQLite: %s → %s", parquet_path, db_path)
    import pandas as pd
    df = pd.read_parquet(str(parquet_path))

    # Verify schema
    logger.info("Parquet columns: %s", df.columns.tolist())
    logger.info("Sample row: %s", df.iloc[0].to_dict())

    # Extract names
    logger.info("Extracting names from persona text...")
    df["name"] = df["persona"].apply(extract_name)

    # Map to expected column names
    column_map = {
        "skills_and_expertise_list": "skills_and_expertise_list",
        "hobbies_and_interests_list": "hobbies_and_interests_list",
        "career_goals_and_ambitions": "career_goals_and_ambitions",
        "education_level": "education_level",
    }

    # Ensure all expected columns exist, add empty ones if missing
    expected_cols = [
        "uuid", "name", "professional_persona", "sports_persona", "arts_persona",
        "travel_persona", "culinary_persona", "persona", "cultural_background",
        "skills_and_expertise", "skills_and_expertise_list", "hobbies_and_interests",
        "hobbies_and_interests_list", "career_goals_and_ambitions", "sex", "age",
        "marital_status", "education_level", "occupation", "region", "area",
        "prefecture", "country"
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    df_to_save = df[expected_cols]

    # Write to SQLite
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.executescript(PERSONA_DDL)
    df_to_save.to_sql("personas", conn, if_exists="replace", index=False, chunksize=10000)
    # Re-create indexes after replace
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_sex ON personas(sex);
        CREATE INDEX IF NOT EXISTS idx_age ON personas(age);
        CREATE INDEX IF NOT EXISTS idx_prefecture ON personas(prefecture);
        CREATE INDEX IF NOT EXISTS idx_region ON personas(region);
        CREATE INDEX IF NOT EXISTS idx_occupation ON personas(occupation);
        CREATE INDEX IF NOT EXISTS idx_education ON personas(education_level);
    """)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
    conn.close()
    logger.info("Persona DB loaded: %d rows", count)

    # Print sample for verification
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT uuid, name, sex, age, occupation, prefecture FROM personas LIMIT 3").fetchall()
    for r in rows:
        logger.info("Sample: %s", dict(r))
    conn.close()

    _ensure_financial_ext_table()


def _ensure_financial_ext_table():
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.executescript(FINANCIAL_EXT_DDL)
    conn.commit()
    conn.close()


def _download_dataset(parquet_path: Path):
    """Download dataset from HuggingFace and save as parquet."""
    from datasets import load_dataset
    logger.info("Downloading nvidia/Nemotron-Personas-Japan from HuggingFace (~1.7GB)...")
    ds = load_dataset(settings.persona_hf_dataset, split="train")
    logger.info("Downloaded. Columns: %s, Rows: %d", ds.column_names, len(ds))
    os.makedirs(parquet_path.parent, exist_ok=True)
    ds.to_parquet(str(parquet_path))
    logger.info("Saved to %s", parquet_path)


def init_db():
    """Initialize all databases. Called at server startup."""
    _load_personas_to_sqlite()
    _create_history_db()
