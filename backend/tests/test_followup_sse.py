import asyncio
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
from db import _create_history_db
from routers import followup
from prompts import build_followup_system_prompt


@pytest.fixture()
def followup_client(tmp_path):
    history_db = str(tmp_path / "history.db")

    orig_hist = settings.history_db_path
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

    settings.history_db_path = orig_hist


@pytest.fixture()
def followup_client_with_thinking(tmp_path):
    """Fixture that seeds two runs: one with enable_thinking=1 and one with enable_thinking=0."""
    history_db = str(tmp_path / "history.db")

    orig_hist = settings.history_db_path
    settings.history_db_path = history_db

    _create_history_db()

    hist_conn = sqlite3.connect(history_db)
    for run_id, enable_thinking in [("run-think-on", 1), ("run-think-off", 0)]:
        hist_conn.execute(
            "INSERT INTO survey_runs (id, created_at, survey_theme, questions_json,"
            " filter_config_json, persona_count, status, enable_thinking)"
            " VALUES (?, datetime('now'), ?, ?, '{}', 1, 'completed', ?)",
            (run_id, "テスト", json.dumps(["質問1"]), enable_thinking),
        )
        hist_conn.execute(
            "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
            " persona_full_json, question_index, question_text, answer, score, created_at)"
            " VALUES (?, ?, ?, '{}', 0, ?, ?, 4, datetime('now'))",
            (run_id, "p1", "テスト太郎 30歳", "質問1", "回答テスト"),
        )
    hist_conn.commit()
    hist_conn.close()

    app = FastAPI()
    app.include_router(followup.router)
    with TestClient(app) as c:
        yield c

    settings.history_db_path = orig_hist


def test_bug3_followup_passes_enable_thinking_from_run(followup_client_with_thinking):
    """Bug 3: followup passes enable_thinking from the run's DB record to stream_followup_answer."""
    captured_calls: list[dict] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_calls.append({"enable_thinking": enable_thinking})
        yield ("answer", "テスト回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        for run_id, expected in [("run-think-on", True), ("run-think-off", False)]:
            captured_calls.clear()
            resp = followup_client_with_thinking.post(
                "/api/followup/ask",
                json={"run_id": run_id, "persona_uuid": "p1", "question": "質問"},
            )
            assert resp.status_code == 200, resp.text
            assert len(captured_calls) == 1, "stream_followup_answer should be called once"
            assert captured_calls[0]["enable_thinking"] == expected, (
                f"run {run_id}: expected enable_thinking={expected}, "
                f"got {captured_calls[0]['enable_thinking']}"
            )


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


def test_followup_prompt_uses_structured_memory_not_raw_qa_transcript():
    """Follow-up prompt should not embed previous answers as raw Q:/A: transcript lines."""
    prompt = build_followup_system_prompt(
        persona={
            "name": "テスト太郎",
            "age": 42,
            "sex": "男",
            "prefecture": "東京都",
            "region": "関東",
            "occupation": "会社員",
            "education_level": "大学卒",
            "marital_status": "既婚",
            "persona": "テスト用人物像",
        },
        financial_ext=None,
        survey_theme="AI投資アドバイザー",
        previous_answers=[
            {
                "question_index": 0,
                "question_text": "利用にあたっての懸念点をお聞かせください",
                "answer": "【懸念点:3】個人情報の取り扱いが心配です。",
            },
        ],
    )

    assert "\nQ1:" not in prompt
    assert "\nA:" not in prompt
    assert "過去アンケート回答" in prompt


def test_followup_persists_assistant_fallback_on_cancelled_stream(followup_client):
    """Cancelled follow-up streams must still leave a paired assistant row in history."""
    async def mock_stream(*args, **kwargs):
        raise asyncio.CancelledError()
        yield

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "キャンセル時の保存確認",
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-2][0] == "user"
    assert rows[-1][0] == "assistant"
    assert "中断" in rows[-1][1] or "取得できません" in rows[-1][1]


def test_followup_suggestions_endpoint_returns_questions_and_excludes_asked_items(followup_client):
    """Suggestions endpoint should return 3 questions and exclude existing follow-up user prompts."""
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "すでに聞いた質問"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "回答"),
    )
    hist_conn.commit()
    hist_conn.close()

    with patch(
        "routers.followup.generate_followup_suggestions",
        return_value=["すでに聞いた質問", "新しい質問1", "新しい質問2", "新しい質問3"],
    ):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["questions"] == ["新しい質問1", "新しい質問2", "新しい質問3"]


def test_followup_does_not_retry_or_switch_thinking_modes_on_english_meta_reasoning(followup_client):
    """English meta-reasoning should not trigger a hidden retry or leak into the final answer."""
    calls: list[bool] = []

    async def mock_stream(*args, **kwargs):
        calls.append(kwargs["enable_thinking"])
        yield ("answer", "Okay, let's see. ")
        yield ("answer", "The user is asking about fees.")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "料金面で気になる点はありますか？",
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert calls == [True]
    assert "Okay, let's see." not in resp.text
    assert "The user is asking about fees." not in resp.text
    assert "（回答を取得できませんでした。もう一度お試しください。）" in resp.text


def test_followup_strips_malformed_assistant_turn_from_persisted_answer(followup_client):
    """Malformed parser output should not be persisted with a duplicated assistant turn."""

    async def mock_stream(*args, **kwargs):
        yield ("answer", "assistant\n")
        yield ("answer", "ユーザーの関心は手数料の透明性です。")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "料金面で気になる点はありますか？",
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert "event: done" in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0][0] == "user"
    assert rows[1][0] == "assistant"
    assert rows[0][1] == "料金面で気になる点はありますか？"
    assert rows[1][1].strip()
    assert not rows[1][1].lstrip().startswith("assistant")
    assert "ユーザーの関心は手数料の透明性です。" in rows[1][1]


def test_followup_skips_contaminated_assistant_history_when_building_messages(followup_client):
    """Persisted English meta-reasoning should not be fed back into later follow-up turns."""
    conn = sqlite3.connect(settings.history_db_path)
    try:
        conn.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
            (
                "run1",
                "p1",
                "Okay, let's see. The user is asking about fees and I need to recall the context.",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(_system_prompt, messages, **kwargs):
        captured_messages.append(messages)
        yield ("answer", "手数料が分かりやすければ検討しやすいです。")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "料金面で気になる点はありますか？",
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert len(captured_messages) == 1
    assert captured_messages[0] == [
        {"role": "user", "content": "料金面で気になる点はありますか？"},
    ]


def test_followup_replaces_english_meta_reasoning_only_answer_with_fallback(followup_client):
    """Meta-reasoning-only follow-up output must not be persisted as the assistant answer."""

    async def mock_stream(*args, **kwargs):
        yield ("answer", "Okay, let's see. The user is asking about fees.")
        yield ("answer", " First, I need to recall the context.")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "料金面で気になる点はありますか？",
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert "event: done" in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-2][0] == "user"
    assert rows[-1][0] == "assistant"
    assert rows[-1][1] == "（回答を取得できませんでした。もう一度お試しください。）"
