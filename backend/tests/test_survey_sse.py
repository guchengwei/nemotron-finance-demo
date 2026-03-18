import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import _create_history_db
from persona_store import PersonaStore
from routers import survey


def _setup_history_db(tmp_path):
    """Create a minimal history DB."""
    history_db = str(tmp_path / "history.db")
    with patch.object(settings, "history_db_path", history_db):
        _create_history_db()
    return history_db


@pytest.fixture()
def survey_client(tmp_path):
    history_db = _setup_history_db(tmp_path)
    orig_hist = settings.history_db_path
    settings.history_db_path = history_db

    df = pd.DataFrame([{
        "uuid": "p1", "name": "テスト太郎", "persona": "テストペルソナ",
        "country": "日本", "sex": "男", "age": 30, "marital_status": "未婚",
        "education_level": "大学卒", "occupation": "会社員", "region": "関東",
        "area": "都心", "prefecture": "東京都", "professional_persona": "会社員",
        "cultural_background": "日本", "skills_and_expertise": "営業",
        "skills_and_expertise_list": None, "hobbies_and_interests": "読書",
        "hobbies_and_interests_list": None, "career_goals_and_ambitions": "昇進",
        "sports_persona": None, "arts_persona": None, "travel_persona": None,
        "culinary_persona": None, "financial_literacy": None,
        "investment_experience": None, "financial_concerns": None,
        "annual_income_bracket": None, "asset_bracket": None,
        "primary_bank_type": None,
    }])
    store = PersonaStore(df)

    app = FastAPI()
    app.include_router(survey.router)
    with patch("routers.survey._get_persona", side_effect=lambda pid: store.get_persona(pid)):
        with TestClient(app) as c:
            yield c

    settings.history_db_path = orig_hist


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
