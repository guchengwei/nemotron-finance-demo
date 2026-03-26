"""Tests for followup suggestion generation robustness."""
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import _create_history_db
from routers import followup


@pytest.fixture()
def followup_client(tmp_path):
    history_db = str(tmp_path / "history.db")
    orig_hist = settings.history_db_path
    settings.history_db_path = history_db
    _create_history_db()

    conn = sqlite3.connect(history_db)
    conn.execute(
        "INSERT INTO survey_runs (id, created_at, survey_theme, questions_json,"
        " filter_config_json, persona_count, status)"
        " VALUES (?, datetime('now'), ?, ?, '{}', 1, 'completed')",
        ("run1", "テスト", json.dumps(["質問1"])),
    )
    conn.execute(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
        " persona_full_json, question_index, question_text, answer, score, created_at)"
        " VALUES (?, ?, ?, '{}', 0, ?, ?, 4, datetime('now'))",
        ("run1", "p1", "テスト太郎 30歳", "質問1", "回答テスト"),
    )
    conn.commit()
    conn.close()

    app = FastAPI()
    app.include_router(followup.router)
    with TestClient(app) as c:
        yield c

    settings.history_db_path = orig_hist


# ---------------------------------------------------------------------------
# Cycle 1 — dict-type items must be rejected / string-extracted
# ---------------------------------------------------------------------------


def test_suggestion_generator_rejects_dict_items_when_llm_returns_objects(followup_client):
    """When the LLM returns JSON objects instead of plain strings, only clean plain
    string items must appear in the result. Dict items must never reach the UI."""

    class _FakeCompletions:
        async def create(self, **kwargs):
            content = json.dumps([
                {"question": "質問A", "reason": "理由"},
                "質問B",
                "質問C",
                "質問D",
            ])
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    with patch("llm.get_client", return_value=_FakeClient()):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    # No question must contain dict-like syntax
    assert all(isinstance(q, str) and "{" not in q and "}" not in q for q in questions)
    # The plain string items must survive
    assert "質問B" in questions


# ---------------------------------------------------------------------------
# Cycle 2 — numbered-line output parsed correctly
# ---------------------------------------------------------------------------


def test_suggestion_generator_parses_numbered_lines_when_llm_ignores_json_format(followup_client):
    """When the LLM outputs numbered lines instead of a JSON array, the three
    questions must still be extracted correctly."""

    class _FakeCompletions:
        async def create(self, **kwargs):
            content = (
                "1. 投資経験はどのくらいですか？\n"
                "2. 老後の備えをどう考えますか？\n"
                "3. 手数料の許容範囲は？"
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    with patch("llm.get_client", return_value=_FakeClient()):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    assert len(questions) == 3
    assert "投資経験はどのくらいですか？" in questions
    assert "老後の備えをどう考えますか？" in questions
    assert "手数料の許容範囲は？" in questions


# ---------------------------------------------------------------------------
# Cycle 3 — prompt uses numbered-line format, not JSON array
# ---------------------------------------------------------------------------


def test_followup_suggestions_prompt_requests_numbered_list_not_json_array():
    """The FOLLOWUP_SUGGESTIONS_PROMPT must instruct the model to output numbered
    lines, not a JSON array, to prevent the model from drifting to object format."""
    from prompts import FOLLOWUP_SUGGESTIONS_PROMPT

    # Must contain a numbered-list example or instruction
    assert "1." in FOLLOWUP_SUGGESTIONS_PROMPT or "番号付き" in FOLLOWUP_SUGGESTIONS_PROMPT
    # Must NOT ask for a JSON array
    assert "JSON配列" not in FOLLOWUP_SUGGESTIONS_PROMPT
