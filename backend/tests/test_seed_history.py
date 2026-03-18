import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings
from db import PERSONA_DDL, _create_history_db


@pytest.fixture()
def history_db(tmp_path):
    """Create a minimal history DB for seed tests."""
    db_path = str(tmp_path / "history.db")
    with patch.object(settings, "history_db_path", db_path):
        _create_history_db()
    return db_path


@pytest.fixture()
def persona_db(tmp_path):
    """Create a minimal persona DB with one row."""
    db_path = str(tmp_path / "personas.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(PERSONA_DDL)
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
    with patch.object(settings, "db_path", persona_db), \
         patch.object(settings, "history_db_path", history_db):
        from scripts.seed_demo_history import seed_history
        import importlib
        import scripts.seed_demo_history as mod
        importlib.reload(mod)
        mod.seed_history()

    conn = sqlite3.connect(history_db)
    count = conn.execute("SELECT COUNT(*) FROM survey_runs").fetchone()[0]
    conn.close()
    assert count > 0, "Seeding should have created at least one survey run"
