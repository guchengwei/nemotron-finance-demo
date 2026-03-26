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
from llm import stream_followup_answer
from models import FollowUpRequest
from routers import followup
from prompts import build_followup_system_prompt


# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

SAMPLE_PERSONA = {
    "name": "テスト太郎",
    "age": 42,
    "sex": "男",
    "prefecture": "東京都",
    "region": "関東",
    "occupation": "会社員",
    "education_level": "大学卒",
    "marital_status": "既婚",
    "persona": "テスト用人物像",
}

SAMPLE_FIN_EXT = {
    "financial_literacy": "中級者",
    "investment_experience": "株式投資の経験あり",
    "financial_concerns": "老後資金",
    "annual_income_bracket": "500-800万",
    "asset_bracket": "500-2000万",
    "primary_bank_type": "メガバンク",
}

SAMPLE_ANSWERS = [
    {"question_index": 0, "question_text": "質問1", "answer": "回答1", "score": 3}
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_history(db_path: str, messages: list[tuple[str, str]]) -> None:
    """Insert (role, content) pairs into followup_chats for run1/p1."""
    conn = sqlite3.connect(db_path)
    for role, content in messages:
        conn.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, ?, ?)",
            ("run1", "p1", role, content),
        )
    conn.commit()
    conn.close()


def _capture_stream_messages(followup_client, question: str) -> list[dict]:
    """Returns the messages list that was passed to stream_followup_answer."""
    captured_messages: list[list[dict]] = []

    async def mock_stream(system_prompt, messages, enable_thinking=True):
        captured_messages.append(messages)
        yield ("answer", "テスト回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": question},
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200, resp.text
    return captured_messages[0] if captured_messages else []


def _capture_llm_call() -> dict:
    """Run stream_followup_answer and capture the kwargs sent to client.chat.completions.create."""
    from types import SimpleNamespace as _SN

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

    with patch("llm.get_client", return_value=_FakeClient()):
        asyncio.run(_run())

    return captured


# ---------------------------------------------------------------------------
# Tests kept from original file
# ---------------------------------------------------------------------------

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
    assert "先ほどのアンケート" in prompt


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


# ---------------------------------------------------------------------------
# Step 1A: System prompt tests (RED until Step 2 implemented)
# ---------------------------------------------------------------------------

def test_followup_system_prompt_is_concise():
    """New prompt must not contain attribute sub-section headers or numbered rules block."""
    prompt = build_followup_system_prompt(
        persona=SAMPLE_PERSONA,
        financial_ext=SAMPLE_FIN_EXT,
        survey_theme="テスト",
        previous_answers=SAMPLE_ANSWERS,
    )
    for header in ["【職業面】", "【文化的背景】", "【スキル・専門性】", "【趣味・関心事】", "【キャリア目標】"]:
        assert header not in prompt, f"Sub-section header still present: {header}"
    assert "【回答ルール】" not in prompt
    assert "テスト用人物像" in prompt
    assert "テスト" in prompt  # survey theme present


def test_followup_system_prompt_strips_score_from_previous_answers():
    """Score prefixes like 【評価:3】 should be stripped from previous answers in prompt."""
    prompt = build_followup_system_prompt(
        persona=SAMPLE_PERSONA,
        financial_ext=None,
        survey_theme="テスト",
        previous_answers=[{"question_index": 0, "question_text": "Q1", "answer": "【評価:3】心配です"}],
    )
    assert "【評価" not in prompt


# ---------------------------------------------------------------------------
# Step 1B: LLM parameter tests (RED until Step 3 implemented)
# ---------------------------------------------------------------------------

def test_followup_default_temperature_is_0_7():
    from config import Settings
    assert Settings().followup_temperature == 0.7


def test_followup_default_max_tokens_is_512():
    from config import Settings
    assert Settings().followup_max_tokens == 512


def test_followup_no_repetition_or_frequency_penalty():
    """stream_followup_answer must not send repetition_penalty or frequency_penalty."""
    captured = _capture_llm_call()
    assert "repetition_penalty" not in captured.get("extra_body", {}), (
        f"repetition_penalty should not be sent; extra_body={captured.get('extra_body')}"
    )
    assert captured.get("frequency_penalty", 0) == 0, (
        f"frequency_penalty should be 0, got {captured.get('frequency_penalty')}"
    )
    assert "stop" not in captured or captured["stop"] is None, (
        f"stop tokens should not be sent; stop={captured.get('stop')}"
    )


# ---------------------------------------------------------------------------
# Step 1C: Message construction tests (RED until Step 4 implemented)
# ---------------------------------------------------------------------------

def test_followup_sends_raw_history_directly(followup_client):
    """History should be sent as-is from DB, no sanitization."""
    _seed_history(settings.history_db_path, [
        ("user", "過去の質問1"),
        ("assistant", "過去の回答1"),
    ])
    captured = _capture_stream_messages(followup_client, "今回の質問")
    assert captured == [
        {"role": "user", "content": "過去の質問1"},
        {"role": "assistant", "content": "過去の回答1"},
        {"role": "user", "content": "今回の質問"},
    ]


def test_followup_limits_history_to_max_messages(followup_client):
    """Only last N messages should be sent to LLM."""
    _seed_history(settings.history_db_path, [
        (role, f"msg{i}") for i in range(15) for role in ["user", "assistant"]
    ])
    captured = _capture_stream_messages(followup_client, "最新質問")
    assert len(captured) <= settings.followup_max_history_messages + 1


def test_followup_streams_without_retry(followup_client):
    """stream_followup_answer should be called exactly once — no retry logic."""
    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        yield ("answer", "正常回答")

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={"run_id": "run1", "persona_uuid": "p1", "question": "テスト"},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200, resp.text
    assert call_count == 1, f"Expected exactly 1 call, got {call_count}"


def test_followup_includes_all_history_roles(followup_client):
    """Dangling (unpaired) user messages in history should be included — no pairing logic."""
    _seed_history(settings.history_db_path, [
        ("user", "質問1"),
        ("assistant", "回答1"),
        ("user", "未回答の質問"),  # dangling — no assistant turn
    ])
    captured = _capture_stream_messages(followup_client, "今回の質問")
    assert len(captured) == 4, f"Expected 4 messages, got {len(captured)}: {captured}"
    assert captured[2] == {"role": "user", "content": "未回答の質問"}
