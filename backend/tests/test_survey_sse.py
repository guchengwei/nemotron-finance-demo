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
from routers import survey


def _setup_dbs(tmp_path):
    """Create minimal persona + history DBs."""
    persona_db = str(tmp_path / "personas.db")
    history_db = str(tmp_path / "history.db")

    from db import PERSONA_DDL, _create_history_db
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

    with patch.object(settings, "history_db_path", history_db):
        _create_history_db()

    return persona_db, history_db


@pytest.fixture()
def survey_client(tmp_path):
    persona_db, history_db = _setup_dbs(tmp_path)
    original_db = settings.db_path
    original_hist = settings.history_db_path
    settings.db_path = persona_db
    settings.history_db_path = history_db

    app = FastAPI()
    app.include_router(survey.router)
    with TestClient(app) as c:
        yield c

    settings.db_path = original_db
    settings.history_db_path = original_hist


def test_survey_emits_error_event_on_per_question_llm_failure(survey_client):
    """When LLM fails on a question, SSE must include an error indicator."""

    async def mock_stream(*args, **kwargs):
        raise ConnectionError("vLLM unreachable")
        yield  # make it a generator

    with patch("routers.survey.stream_survey_answer", side_effect=mock_stream):
        resp = survey_client.post(
            "/api/survey/run",
            json={
                "persona_ids": ["p1"],
                "survey_theme": "テスト",
                "questions": ["テスト質問"],
            },
            headers={"Accept": "text/event-stream"},
        )

    # Parse SSE events
    events = []
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            events.append(line[7:].strip())

    # Must have either persona_error or a persona_answer with error indicator
    has_error_signal = "persona_error" in events
    assert has_error_signal, (
        f"Expected persona_error event when LLM fails per-question, got: {events}"
    )
