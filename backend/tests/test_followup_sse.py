import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import PERSONA_DDL, _create_history_db
from routers import followup


@pytest.fixture()
def followup_client(tmp_path):
    history_db = str(tmp_path / "history.db")
    persona_db = str(tmp_path / "personas.db")

    conn = sqlite3.connect(persona_db)
    conn.executescript(PERSONA_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()

    orig_db = settings.db_path
    orig_hist = settings.history_db_path
    settings.db_path = persona_db
    settings.history_db_path = history_db

    _create_history_db()

    # Seed a survey run so followup has context
    hist_conn = sqlite3.connect(history_db)
    hist_conn.execute(
        "INSERT INTO survey_runs (id, created_at, survey_theme, questions_json,"
        " filter_config_json, persona_count, status)"
        " VALUES (?, datetime('now'), ?, ?, '{}', 1, 'completed')",
        ("run1", "テスト", json.dumps(["質問1"])),
    )
    hist_conn.execute(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
        " persona_full_json, question_index, question_text, answer, score, created_at)"
        " VALUES (?, ?, ?, '{}', 0, ?, ?, 4, datetime('now'))",
        ("run1", "p1", "テスト太郎 30歳", "質問1", "回答テスト"),
    )
    hist_conn.commit()
    hist_conn.close()

    app = FastAPI()
    app.include_router(followup.router)
    with TestClient(app) as c:
        yield c

    settings.db_path = orig_db
    settings.history_db_path = orig_hist


def test_followup_emits_error_event_on_llm_failure(followup_client):
    """When LLM stream fails, must emit an error event, not hang."""
    async def mock_stream(*args, **kwargs):
        raise ConnectionError("vLLM unreachable")
        yield  # make it a generator

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "テスト質問",
            },
            headers={"Accept": "text/event-stream"},
        )

    events = []
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            events.append(line[7:].strip())

    assert "error" in events or "done" in events, (
        f"Expected error or done event, got: {events}"
    )
