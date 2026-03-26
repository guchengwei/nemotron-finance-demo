"""Tests for followup suggestion generation robustness."""
import json
import sqlite3
import sys
import asyncio
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
from llm import generate_followup_suggestions, normalize_followup_question


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


def test_generate_followup_suggestions_uses_recent_user_questions_in_prompt():
    """The generator should build prompt context from recent user questions, not
    generic mixed chat-history wording."""

    captured = {}

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="1. 質問A\n2. 質問B\n3. 質問C"))]
            )

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    recent_user_questions = [
        {"role": "user", "content": "最近の質問1"},
        {"role": "user", "content": "最近の質問2"},
        {"role": "user", "content": "最近の質問3"},
    ]

    with patch("llm.get_client", return_value=_FakeClient()):
        questions = asyncio.run(generate_followup_suggestions(
            survey_theme="テストテーマ",
            persona={"name": "山田太郎", "age": 30, "occupation": "会社員", "prefecture": "東京都"},
            previous_answers=[
                {"question_index": 0, "question_text": "設問1", "answer": "回答1"},
            ],
            recent_user_questions=recent_user_questions,
            excluded_questions=set(),
        ))

    assert questions == ["質問A", "質問B", "質問C"]
    prompt = captured["messages"][0]["content"]
    assert "最近のユーザー質問" in prompt
    assert "これまでの深掘り会話" not in prompt
    assert "最近の質問1" in prompt and "最近の質問3" in prompt


def test_generate_followup_suggestions_keeps_global_exclusions_outside_visible_slice():
    """Questions excluded from the full asked-question set must stay excluded even
    when they are not part of the visible recent-user-question slice."""

    class _FakeCompletions:
        async def create(self, **kwargs):
            content = (
                "1. 既に聞いた古い質問\n"
                "2. 手数料はどのくらい許容できますか？\n"
                "3. どんな情報があれば判断しやすいですか？"
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    excluded_old_question = "既に聞いた古い質問"
    recent_user_questions = [
        {"role": "user", "content": "最近の質問1"},
        {"role": "user", "content": "最近の質問2"},
        {"role": "user", "content": "最近の質問3"},
    ]

    with patch("llm.get_client", return_value=_FakeClient()):
        questions = asyncio.run(generate_followup_suggestions(
            survey_theme="テストテーマ",
            persona={"name": "山田太郎", "age": 30, "occupation": "会社員", "prefecture": "東京都"},
            previous_answers=[
                {"question_index": 0, "question_text": "設問1", "answer": "回答1"},
            ],
            recent_user_questions=recent_user_questions,
            excluded_questions={normalize_followup_question(excluded_old_question)},
        ))

    assert len(questions) == 3
    assert all(normalize_followup_question(q) != excluded_old_question for q in questions)


def test_generate_followup_suggestions_backfills_weak_llm_output_to_three_clean_suggestions():
    """Weak or partial LLM output should still be normalized and backfilled to
    three clean suggestions."""

    class _FakeCompletions:
        async def create(self, **kwargs):
            content = (
                "1. 具体的にはどのような点が気になりますか？\n"
                "2. 具体的にはどのような点が気になりますか？\n"
                "3. {\"question\": \"無効な形式\"}"
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    recent_user_questions = [
        {"role": "user", "content": "最近の質問1"},
        {"role": "user", "content": "最近の質問2"},
        {"role": "user", "content": "最近の質問3"},
    ]

    with patch("llm.get_client", return_value=_FakeClient()):
        questions = asyncio.run(generate_followup_suggestions(
            survey_theme="テストテーマ",
            persona={"name": "山田太郎", "age": 30, "occupation": "会社員", "prefecture": "東京都"},
            previous_answers=[
                {"question_index": 0, "question_text": "設問1", "answer": "回答1"},
            ],
            recent_user_questions=recent_user_questions,
            excluded_questions=set(),
        ))

    assert len(questions) == 3
    assert len({normalize_followup_question(q) for q in questions}) == 3
    assert all("{" not in q and "}" not in q for q in questions)
