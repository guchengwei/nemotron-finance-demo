import asyncio
import json
import sqlite3
import threading
import time
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
from routers import history, survey


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
    app.include_router(history.router)
    with patch("persona_store.get_store", return_value=store):
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
            headers={"Idempotency-Key": "question-failure"},
        )
        assert resp.status_code == 202
        resp = survey_client.get(f"/api/survey/stream/{resp.json()['run_id']}")

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
    assert "vLLM unreachable" not in resp.text
    with sqlite3.connect(settings.history_db_path) as connection:
        answer = connection.execute(
            "SELECT answer, outcome, error_code, error_message FROM survey_answers"
        ).fetchone()
    assert answer == (None, "failed", "llm_unreachable", "回答サービスに接続できませんでした。")


def _start(survey_client, key="run-key", **overrides):
    body = {
        "persona_ids": ["p1"],
        "survey_theme": "テスト",
        "questions": ["テスト質問"],
        **overrides,
    }
    return survey_client.post("/api/survey/run", json=body, headers={"Idempotency-Key": key})


def _wait_for_terminal(run_id: str) -> str:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with sqlite3.connect(settings.history_db_path) as connection:
            row = connection.execute("SELECT status FROM survey_runs WHERE id = ?", [run_id]).fetchone()
        if row and row[0] != "running":
            return row[0]
        time.sleep(0.01)
    raise AssertionError("run did not become terminal")


def test_start_is_idempotent_and_rejects_mismatched_reuse(survey_client):
    first = _start(survey_client, "same-key")
    assert first.status_code == 202
    second = _start(survey_client, "same-key")
    assert second.status_code == 202
    assert second.json()["run_id"] == first.json()["run_id"]

    mismatch = _start(survey_client, "same-key", survey_theme="別テーマ")
    assert mismatch.status_code == 409
    with sqlite3.connect(settings.history_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM survey_runs").fetchone()[0] == 1


def test_invalid_request_creates_no_run(survey_client):
    response = _start(survey_client, "invalid", persona_ids=["p1", "p1"])
    assert response.status_code == 422
    with sqlite3.connect(settings.history_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM survey_runs").fetchone()[0] == 0


def test_run_completes_without_an_observer_and_replays_gaplessly(survey_client):
    started = _start(survey_client, "detached")
    run_id = started.json()["run_id"]
    assert _wait_for_terminal(run_id) == "completed"

    first = survey_client.get(f"/api/survey/stream/{run_id}")
    second = survey_client.get(f"/api/survey/stream/{run_id}")
    first_ids = [int(line[4:]) for line in first.text.splitlines() if line.startswith("id: ")]
    second_ids = [int(line[4:]) for line in second.text.splitlines() if line.startswith("id: ")]
    assert first_ids == list(range(1, len(first_ids) + 1))
    assert second_ids == first_ids
    assert first.text.count("event: survey_complete") == 1

    cursor = first_ids[-2]
    replay = survey_client.get(f"/api/survey/stream/{run_id}?last_event_id={cursor}")
    replay_ids = [int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")]
    assert replay_ids == [first_ids[-1]]


def test_cancellation_is_idempotent_retains_state_and_allows_cascade_delete(survey_client):
    async def slow_stream(*args, **kwargs):
        await asyncio.sleep(60)
        yield "answer", "never reached"

    with patch("routers.survey.stream_survey_answer", side_effect=slow_stream):
        started = _start(survey_client, "cancelled")
        run_id = started.json()["run_id"]
        assert survey_client.delete(f"/api/history/{run_id}").status_code == 409
        first = survey_client.post(f"/api/survey/{run_id}/cancel")
        second = survey_client.post(f"/api/survey/{run_id}/cancel")
        assert first.status_code == 202
        assert second.status_code == 202
        assert _wait_for_terminal(run_id) == "cancelled"

    stream = survey_client.get(f"/api/survey/stream/{run_id}")
    assert stream.text.count("event: survey_cancelled") == 1
    payloads = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
    terminal = payloads[-1]
    assert terminal["completed"] + terminal["failed"] + terminal["not_completed"] == terminal["total"]
    assert survey_client.delete(f"/api/history/{run_id}").status_code == 200
    with sqlite3.connect(settings.history_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_events WHERE run_id = ?", [run_id]).fetchone()[0] == 0


def test_legacy_terminal_history_is_explicitly_not_replayable(survey_client):
    with sqlite3.connect(settings.history_db_path) as connection:
        connection.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, status) "
            "VALUES ('legacy', 'theme', '[]', 'completed')"
        )
        connection.commit()
    response = survey_client.get("/api/survey/stream/legacy")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "replay_unavailable"


def test_question_generation_happens_after_durable_creation(survey_client):
    generation_started = threading.Event()
    release_generation = threading.Event()

    async def delayed_questions(*args, **kwargs):
        generation_started.set()
        await asyncio.to_thread(release_generation.wait)
        return ["生成された質問"]

    with patch("routers.survey.generate_questions", side_effect=delayed_questions):
        response = _start(survey_client, "generated", questions=None)
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        with sqlite3.connect(settings.history_db_path) as connection:
            row = connection.execute(
                "SELECT questions_json, status FROM survey_runs WHERE id = ?", [run_id]
            ).fetchone()
            snapshots = connection.execute(
                "SELECT COUNT(*) FROM run_personas WHERE run_id = ?", [run_id]
            ).fetchone()[0]
            first_event = connection.execute(
                "SELECT seq, event_type FROM run_events WHERE run_id = ?", [run_id]
            ).fetchone()
        assert row == ("[]", "running")
        assert snapshots == 1
        assert first_event == (1, "run_created")
        release_generation.set()
        assert _wait_for_terminal(run_id) == "completed"
