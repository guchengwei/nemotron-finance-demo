import asyncio
import json
import sqlite3
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import _create_history_db
from models import FollowUpRequest
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


def test_followup_prompt_does_not_reuse_survey_scoring_rules_or_scored_memory():
    """Follow-up prompt should not carry survey-only scoring instructions into chat."""
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
                "answer": "【評価:3】個人情報の取り扱いが心配です。",
            },
        ],
    )

    assert "フォーマット: 「【評価: X】理由の説明...」" not in prompt
    assert "回答要旨: 【評価:" not in prompt


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


def test_followup_suggestions_backfill_after_older_asked_question_is_filtered(followup_client):
    """Older asked questions outside replayed history must still be excluded during backfill."""
    hist_conn = sqlite3.connect(settings.history_db_path)
    for idx in range(1, 5):
        hist_conn.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
            ("run1", "p1", f"過去の質問{idx}"),
        )
        hist_conn.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
            ("run1", "p1", f"過去の回答{idx}"),
        )
    hist_conn.commit()
    hist_conn.close()

    class _FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='["過去の質問1", "新しい質問1"]'
                        )
                    )
                ]
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
    assert "過去の質問1" not in questions
    assert "新しい質問1" in questions


def test_followup_suggestions_backfill_with_previous_answers_when_canned_pool_is_exhausted(
    followup_client,
):
    """Normal-path backfill should still use previous_answers when canned fallbacks are excluded."""
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
        " persona_full_json, question_index, question_text, answer, score, created_at)"
        " VALUES (?, ?, ?, '{}', 1, ?, ?, 4, datetime('now'))",
        ("run1", "p1", "テスト太郎 30歳", "補助設問A", "補助回答A"),
    )
    hist_conn.execute(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
        " persona_full_json, question_index, question_text, answer, score, created_at)"
        " VALUES (?, ?, ?, '{}', 2, ?, ?, 4, datetime('now'))",
        ("run1", "p1", "テスト太郎 30歳", "補助設問B", "補助回答B"),
    )
    excluded_users = [
        "過去の質問1",
        "質問1",
        "具体的にどの程度の手数料なら許容できますか？",
        "どのような情報があれば判断しやすいですか？",
        "このサービスを知人に勧めますか？その理由は？",
    ]
    for question in excluded_users:
        hist_conn.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
            ("run1", "p1", question),
        )
        hist_conn.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
            ("run1", "p1", f"{question}への回答"),
        )
    hist_conn.commit()
    hist_conn.close()

    class _FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='["過去の質問1", "新しい質問1"]'
                        )
                    )
                ]
            )

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    with patch("llm.get_client", return_value=_FakeClient()):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["questions"] == ["新しい質問1", "補助設問A", "補助設問B"]


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


def test_followup_think_off_replaces_question_echo_only_answer_with_fallback(followup_client_with_thinking):
    """Think-off follow-up should not persist or return the user's question as the assistant answer."""
    question = "資産運用に対する印象を教えてください"
    calls: list[bool] = []

    async def mock_stream(*args, **kwargs):
        calls.append(kwargs["enable_thinking"])
        yield ("answer", question)

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client_with_thinking.post(
            "/api/followup/ask",
            json={
                "run_id": "run-think-off",
                "persona_uuid": "p1",
                "question": question,
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert calls == [False]
    assert question not in resp.text
    assert "（回答を取得できませんでした。もう一度お試しください。）" in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run-think-off", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-2] == ("user", question)
    assert rows[-1] == ("assistant", "（回答を取得できませんでした。もう一度お試しください。）")


def test_followup_replaces_followup_instruction_echo_only_answer_with_fallback(followup_client):
    """Follow-up instruction echo must not be persisted as the assistant answer."""

    async def mock_stream(*args, **kwargs):
        yield (
            "answer",
            "現在の質問にだけ答えてください。先の回答内容を再利用するのではなく、新しい質問への応答として、"
            "この人物の立場から自然に返答してください。【質問】投資信託のオンライン販売プラットフォームで、"
            "特に注目している機能は何ですか？",
        )

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
    assert "（回答を取得できませんでした。もう一度お試しください。）" in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-1][1] == "（回答を取得できませんでした。もう一度お試しください。）"


def test_followup_excludes_dangling_trailing_user_turn_from_replayed_history(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "過去の質問1"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答1"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "未回答の過去質問"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "過去の質問1"},
        {"role": "assistant", "content": "過去の回答1"},
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_replays_normalized_historical_user_turn(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "\n```json```\n「過去の質問です？」"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "過去の質問です？"},
        {"role": "assistant", "content": "過去の回答です"},
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_replays_historical_user_turn_preserves_inline_json_fence_text(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "これは```json```という文字列を含む質問ですか？"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "これは```json```という文字列を含む質問ですか？"},
        {"role": "assistant", "content": "過去の回答です"},
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_replays_historical_user_turn_preserves_ascii_quoted_content(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", '"ETF"'),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": '"ETF"'},
        {"role": "assistant", "content": "過去の回答です"},
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_replays_normalized_multiline_fenced_historical_user_turn(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "```json\n過去の質問です？\n```"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "過去の質問です？"},
        {"role": "assistant", "content": "過去の回答です"},
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_excludes_echoed_assistant_turn_from_replayed_history(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "資産運用に対する印象を教えてください"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "資産運用に対する印象を教えてください"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_repairs_role_gap_after_sanitizer_drops_bad_assistant_row(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "過去の質問1"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "【評価】から始めて回答してください。過去アンケート回答と矛盾しないようにしてください。"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "過去の質問2"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_excludes_toxic_assistant_junk_from_replayed_history(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "【tasksinmoneyGin(-m.,,is(would=-helpshould..."),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "今回の質問"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_messages == [[
        {"role": "user", "content": "今回の質問"},
    ]]


def test_followup_suggestions_normalize_history_but_still_exclude_asked_questions(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "過去の質問1"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答1"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "【tasksinmoneyGin(-m.,,is(would=-helpshould..."),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "未回答の過去質問"),
    )
    hist_conn.commit()
    hist_conn.close()

    captured_chat_history: list[list[dict]] = []

    async def mock_generate_followup_suggestions(
        *,
        survey_theme,
        persona,
        previous_answers,
        chat_history,
        excluded_questions,
    ):
        captured_chat_history.append(chat_history)
        return ["未回答の過去質問", "新しい質問1", "新しい質問2", "新しい質問3"]

    with patch(
        "routers.followup.generate_followup_suggestions",
        side_effect=mock_generate_followup_suggestions,
    ):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    assert captured_chat_history == [[
        {"role": "user", "content": "過去の質問1"},
        {"role": "assistant", "content": "過去の回答1"},
    ]]
    assert resp.json()["questions"] == ["新しい質問1", "新しい質問2", "新しい質問3"]


def test_followup_suggestions_exclude_normalized_historical_question(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "\n```json```\n「過去の質問です？」"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    with patch(
        "routers.followup.generate_followup_suggestions",
        return_value=["過去の質問です？", "新しい質問1", "新しい質問2", "新しい質問3"],
    ):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["questions"] == ["新しい質問1", "新しい質問2", "新しい質問3"]


def test_followup_suggestions_exclude_wrapped_generated_duplicate_question(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "過去の質問です？"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    with patch(
        "routers.followup.generate_followup_suggestions",
        return_value=["「過去の質問です？」", "新しい質問1", "新しい質問2", "新しい質問3"],
    ):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["questions"] == ["新しい質問1", "新しい質問2", "新しい質問3"]


def test_followup_suggestions_exclude_multiline_fenced_historical_duplicate_question(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "```json\n過去の質問です？\n```"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "過去の回答です"),
    )
    hist_conn.commit()
    hist_conn.close()

    with patch(
        "routers.followup.generate_followup_suggestions",
        return_value=["過去の質問です？", "新しい質問1", "新しい質問2", "新しい質問3"],
    ):
        resp = followup_client.post(
            "/api/followup/suggestions",
            json={"run_id": "run1", "persona_uuid": "p1"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["questions"] == ["新しい質問1", "新しい質問2", "新しい質問3"]


def test_clear_followup_history_deletes_only_target_persona_rows(followup_client):
    hist_conn = sqlite3.connect(settings.history_db_path)
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p1", "p1の質問"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p1", "p1の回答"),
    )
    hist_conn.execute(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
        " persona_full_json, question_index, question_text, answer, score, created_at)"
        " VALUES (?, ?, ?, '{}', 0, ?, ?, 4, datetime('now'))",
        ("run1", "p2", "テスト花子 28歳", "質問1", "別人格の回答"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
        ("run1", "p2", "p2の質問"),
    )
    hist_conn.execute(
        "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
        ("run1", "p2", "p2の回答"),
    )
    hist_conn.commit()
    hist_conn.close()

    resp = followup_client.post(
        "/api/followup/clear",
        json={"run_id": "run1", "persona_uuid": "p1"},
    )

    assert resp.status_code == 200, resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        p1_rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
        p2_rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p2"),
        ).fetchall()
    finally:
        conn.close()

    assert p1_rows == []
    assert p2_rows == [("user", "p2の質問"), ("assistant", "p2の回答")]


def test_followup_persists_assistant_fallback_when_stream_generator_closes_early(followup_client):
    async def mock_stream(*args, **kwargs):
        yield ("answer", "途中回答")
        await asyncio.sleep(60)

    async def close_stream_early():
        stream = followup._followup_stream(
            FollowUpRequest(run_id="run1", persona_uuid="p1", question="切断される質問")
        )
        first_event = await stream.__anext__()
        await stream.aclose()
        return first_event

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        first_event = asyncio.run(close_stream_early())

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert "event: token" in first_event
    assert rows[-2][0] == "user"
    assert rows[-2][1] == "切断される質問"
    assert rows[-1][0] == "assistant"
    assert "中断" in rows[-1][1] or "取得できません" in rows[-1][1]


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


def test_followup_strips_leading_score_prefix_from_assistant_answer(followup_client):
    """Tab 5 assistant replies should not persist survey-style score prefixes."""

    async def mock_stream(*args, **kwargs):
        yield ("answer", "【評価:4】手数料が明確なら検討しやすいです。")

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
    assert "【評価" not in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-1][0] == "assistant"
    assert rows[-1][1] == "手数料が明確なら検討しやすいです。"


def test_followup_strips_normalized_question_echo_prefix_from_first_visible_chunk(followup_client):
    raw_question = "\n```json```\n「追加の質問です？」"

    async def mock_stream(*args, **kwargs):
        yield ("answer", "追加の質問です？ 実際の回答です。")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": raw_question,
            },
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert "追加の質問です？" not in resp.text

    done_block = next(
        block for block in resp.text.split("\n\n") if block.startswith("event: done\n")
    )
    done_data = json.loads(
        next(line for line in done_block.splitlines() if line.startswith("data: "))[6:]
    )
    assert done_data["full_answer"] == "実際の回答です。"

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-2][0] == "user"
    assert rows[-2][1] == raw_question
    assert rows[-1][0] == "assistant"
    assert rows[-1][1] == "実際の回答です。"


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


def test_followup_replaces_japanese_rule_echo_only_answer_with_fallback(followup_client):
    """Japanese survey-rule echo must not be persisted as the assistant answer."""

    async def mock_stream(*args, **kwargs):
        yield (
            "answer",
            "【評価】から始めて回答してください。-過去アンケート回答と矛盾しないようにしてください。"
            "-専門用語は適切に使ってください。-敬語を必ず使用してください。",
        )

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
    assert "（回答を取得できませんでした。もう一度お試しください。）" in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-1][1] == "（回答を取得できませんでした。もう一度お試しください。）"


def test_followup_replaces_prompt_section_echo_only_answer_with_fallback(followup_client):
    """Prompt-section echo must not be persisted as a normal Tab 5 answer."""

    async def mock_stream(*args, **kwargs):
        yield (
            "answer",
            "【アンケートテーマ】AIを活用した資産運用アドバイザリーサービスの導入に対する金融機関顧客の反応"
            "【過去アンケート回答】-設問1:AIによる資産運用アドバイスに対する全体的な関心度を教えてください",
        )

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
    assert "（回答を取得できませんでした。もう一度お試しください。）" in resp.text

    conn = sqlite3.connect(settings.history_db_path)
    try:
        rows = conn.execute(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY id",
            ("run1", "p1"),
        ).fetchall()
    finally:
        conn.close()

    assert rows[-1][1] == "（回答を取得できませんでした。もう一度お試しください。）"


def test_followup_replaces_token_soup_only_answer_with_fallback(followup_client):
    """Obvious token-soup follow-up output must not be persisted as a normal assistant answer."""

    async def mock_stream(*args, **kwargs):
        yield ("answer", "【on...((:in.fromofof\\forand-")
        yield ("answer", "chpage's:it,of-of-byyoutoofais,-ofof#include.")

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


def test_followup_replaces_mixed_japanese_token_soup_answer_with_fallback(followup_client):
    """Mixed Japanese-plus-token-soup output must not be persisted as a normal assistant answer."""

    async def mock_stream(*args, **kwargs):
        yield (
            "answer",
            '続afrom0Yandof,,haspatentsusing(to,morein（contempl\\((should((checks...,is:all"ofhad(ofhasan)',
        )

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "続けて確認したい点はありますか？",
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

# ---------------------------------------------------------------------------
# Cycle 2: Config settings + LLM params
# ---------------------------------------------------------------------------

def test_followup_default_max_tokens_is_768():
    """followup_max_tokens default should be 768, not 2048."""
    from config import Settings
    assert Settings().followup_max_tokens == 768


def test_followup_uses_dedicated_temperature_and_penalties():
    """stream_followup_answer must pass followup-specific temperature, repetition_penalty, frequency_penalty."""
    import asyncio
    from types import SimpleNamespace as _SN
    from llm import stream_followup_answer

    captured: dict = {}

    class _FakeAsyncIter:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeAsyncIter()

    class _FakeClient:
        chat = _SN(completions=_FakeCompletions())

    async def _run():
        async for _ in stream_followup_answer(
            "system", [{"role": "user", "content": "test"}], enable_thinking=False
        ):
            pass

    with patch("llm.get_client", return_value=_FakeClient()), \
         patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.llm_concurrency = 4
        mock_settings.followup_temperature = 0.4
        mock_settings.followup_repetition_penalty = 1.15
        mock_settings.followup_frequency_penalty = 0.3
        mock_settings.followup_max_tokens = 768
        mock_settings.vllm_model = "test-model"
        asyncio.run(_run())

    assert captured.get("temperature") == 0.4, f"temperature was {captured.get('temperature')}"
    extra = captured.get("extra_body", {})
    assert extra.get("repetition_penalty") == 1.15, f"extra_body={extra}"
    assert captured.get("frequency_penalty") == 0.3, f"frequency_penalty was {captured.get('frequency_penalty')}"


# ---------------------------------------------------------------------------
# Cycle 3: Streaming repetition detection with retry
# ---------------------------------------------------------------------------

def test_followup_retries_on_repetition_before_emit(followup_client):
    """When repetition fires before first emit, retry transparently (garbage not sent to client)."""
    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Attempt 1: pure repetition garbage before anything is emitted
            yield ("answer", "と思います。" * 60)
        else:
            # Attempt 2: clean answer
            yield ("answer", "投資信託は長期的な資産形成に適しています。")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "投資信託について教えてください"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert call_count == 2, f"Expected 2 calls (retry), got {call_count}"
    # Clean answer should appear in output
    assert "投資信託は長期的な資産形成に適しています" in resp.text
    # Garbage should NOT appear in output
    assert "と思います。と思います。" not in resp.text


def test_followup_truncates_on_repetition_after_emit(followup_client):
    """When repetition fires after first emit, truncate cleanly without sending more garbage."""
    async def mock_stream(*args, **kwargs):
        # First yield a clean prefix to trigger emit
        yield ("answer", "長期投資は非常にお勧めです。詳しく説明しますと、リスク分散の観点から重要です。")
        # Then degenerate into garbage
        yield ("answer", "と思います。" * 60)

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "資産運用について教えてください"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    # Stream should complete (done event emitted)
    assert "event: done" in resp.text
    # Good prefix should be in output
    assert "長期投資は非常にお勧めです" in resp.text
    # Garbage repetition should NOT be in output
    assert "と思います。と思います。" not in resp.text


# ---------------------------------------------------------------------------
# Cycle 4: Enhanced Japanese token soup detection
# ---------------------------------------------------------------------------

def test_token_soup_detects_japanese_repetition_loop():
    """_looks_like_token_soup should detect Japanese repetition loop (10-char substring 3+ times)."""
    from followup_sanitizer import _looks_like_token_soup
    assert _looks_like_token_soup("と思います。" * 30) is True


def test_token_soup_no_false_positive_normal_japanese():
    """_looks_like_token_soup should not flag varied normal Japanese text."""
    from followup_sanitizer import _looks_like_token_soup
    normal = (
        "投資信託は長期的な資産形成に向いています。"
        "リスク許容度に応じた商品選びが大切です。"
        "定期的な積立投資は時間分散効果があります。"
        "老後の資金準備は早めに始めることが重要です。"
    )
    assert _looks_like_token_soup(normal) is False
