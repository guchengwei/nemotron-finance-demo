import sqlite3
from pathlib import Path

import pytest

from config import settings
from db import _create_history_db

# Minimal DDL for the personas table used by seed_demo_history.py
_PERSONAS_DDL = """
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
"""


@pytest.fixture()
def history_db(tmp_path):
    """Create a minimal history DB for seed tests."""
    db_path = str(tmp_path / "history.db")
    orig = settings.history_db_path
    settings.history_db_path = db_path
    _create_history_db()
    settings.history_db_path = orig
    return db_path


@pytest.fixture()
def persona_db(tmp_path):
    """Create a minimal persona DB with one row."""
    db_path = str(tmp_path / "personas.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(_PERSONAS_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("test-uuid", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()
    return db_path


def test_seed_history_opens_configured_db(persona_db, history_db):
    """seed_history must use settings.db_path, not a relative default."""
    orig_db = settings.db_path
    orig_hist = settings.history_db_path
    settings.db_path = persona_db
    settings.history_db_path = history_db
    try:
        import scripts.seed_demo_history as mod
        mod.seed_history()
    finally:
        settings.db_path = orig_db
        settings.history_db_path = orig_hist

    conn = sqlite3.connect(history_db)
    count = conn.execute("SELECT COUNT(*) FROM survey_runs").fetchone()[0]
    conn.close()
    assert count > 0, "Seeding should have created at least one survey run"
