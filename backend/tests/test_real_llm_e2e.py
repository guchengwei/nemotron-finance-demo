"""Real-LLM E2E tests verifying Bugs 1-3 fixes against live vLLM.

Requires:
  - vLLM running at localhost:8000/v1
  - App backend running at localhost:8001

Run with:
  pytest backend/tests/test_real_llm_e2e.py -v -s
"""
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

APP_BASE = "http://localhost:8080"
VLLM_BASE = "http://localhost:8000/v1"


def _vllm_reachable() -> bool:
    try:
        r = requests.get(f"{VLLM_BASE}/models", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _app_reachable() -> bool:
    try:
        r = requests.get(f"{APP_BASE}/ready", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


requires_real_llm = pytest.mark.skipif(
    not _vllm_reachable() or not _app_reachable(),
    reason="Requires live vLLM at :8000 and app at :8001",
)

HISTORY_DB = "/gen-ai/finance/nemotron-finance-demo/data/history.db"

QUESTIONS = [
    "このサービスへの全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）",
    "最も重要だと考える機能や特徴は何ですか？",
    "利用にあたって最も懸念される点は何ですか？",
]

PERSONAS = [
    {"name": "E2E田中", "age": 35, "sex": "男", "occupation": "会社員", "prefecture": "東京都",
     "region": "関東", "financial_literacy": "中級者"},
    {"name": "E2E佐藤", "age": 28, "sex": "女", "occupation": "公務員", "prefecture": "大阪府",
     "region": "関西", "financial_literacy": "初心者"},
    {"name": "E2E鈴木", "age": 52, "sex": "男", "occupation": "自営業", "prefecture": "愛知県",
     "region": "中部", "financial_literacy": "上級者"},
    {"name": "E2E高橋", "age": 44, "sex": "女", "occupation": "会社員", "prefecture": "神奈川県",
     "region": "関東", "financial_literacy": "専門家"},
]


def _seed_multi_question_run(run_id: str, enable_thinking: int = 0) -> None:
    """Insert a completed 3-question run with varying scores per question."""
    conn = sqlite3.connect(HISTORY_DB)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO survey_runs "
            "(id, created_at, survey_theme, questions_json, filter_config_json, persona_count, status, enable_thinking)"
            " VALUES (?, datetime('now'), ?, ?, '{}', ?, 'completed', ?)",
            (
                run_id,
                "AI家計管理アプリのE2Eテスト",
                json.dumps(QUESTIONS, ensure_ascii=False),
                len(PERSONAS),
                enable_thinking,
            ),
        )

        rows = []
        for i, persona_meta in enumerate(PERSONAS):
            p_uuid = str(uuid.uuid4())
            persona = {
                "uuid": p_uuid,
                "financial_extension": {"financial_literacy": persona_meta["financial_literacy"]},
                **persona_meta,
            }
            summary = f"{persona_meta['name']}、{persona_meta['age']}歳"

            # Give each question a DIFFERENT score so Bug 2 fix is verifiable
            q_scores = [
                (i % 5) + 1,           # Q0: cycle 1-5
                ((i + 2) % 5) + 1,     # Q1: offset by 2
                ((i + 4) % 5) + 1,     # Q2: offset by 4
            ]
            q_answers = [
                f"【評価: {q_scores[0]}】手数料と安心感を重視します。",
                f"ポートフォリオ自動管理機能が重要です。",
                f"セキュリティとプライバシーが懸念点です。",
            ]

            for q_idx, (score, answer) in enumerate(zip(q_scores, q_answers)):
                rows.append((
                    run_id, p_uuid, summary,
                    json.dumps(persona, ensure_ascii=False),
                    q_idx, QUESTIONS[q_idx], answer,
                    score if q_idx == 0 else (score if q_idx == 1 else None),  # Q2 has no score
                ))

        conn.executemany(
            "INSERT INTO survey_answers "
            "(run_id, persona_uuid, persona_summary, persona_full_json, "
            "question_index, question_text, answer, score)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _delete_run(run_id: str) -> None:
    conn = sqlite3.connect(HISTORY_DB)
    try:
        conn.execute("DELETE FROM survey_runs WHERE id = ?", (run_id,))
        conn.execute("DELETE FROM survey_answers WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM followup_chats WHERE run_id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()


@requires_real_llm
def test_bug1_report_text_not_empty():
    """Bug 1: group_tendency and conclusion are non-empty with real LLM."""
    run_id = f"e2e-bug1-{uuid.uuid4().hex[:8]}"
    _seed_multi_question_run(run_id)
    try:
        resp = requests.post(f"{APP_BASE}/api/report/generate", json={"run_id": run_id}, timeout=120)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["group_tendency"], "group_tendency should be non-empty with real LLM"
        assert body["conclusion"], "conclusion should be non-empty with real LLM"
        assert len(body["group_tendency"]) > 20, "group_tendency too short"
        assert len(body["conclusion"]) > 20, "conclusion too short"
        # Verify no raw thinking tags leaked through
        assert "<think>" not in body["group_tendency"]
        assert "<think>" not in body["conclusion"]
    finally:
        _delete_run(run_id)


@requires_real_llm
def test_bug2_scores_use_all_questions():
    """Bug 2: overall_score is average across all questions, not Q1-only."""
    run_id = f"e2e-bug2-{uuid.uuid4().hex[:8]}"
    _seed_multi_question_run(run_id)
    try:
        resp = requests.post(f"{APP_BASE}/api/report/generate", json={"run_id": run_id}, timeout=120)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["overall_score"] is not None
        assert body["score_distribution"] is not None

        # Q0 scores: [1,2,3,4] for 4 personas (indices 0-3 mod 5 + 1)
        # Q1 scores: [3,4,5,1] (offset by 2)
        # Per-persona averages should differ from Q1-only
        q0_only_scores = [(i % 5) + 1 for i in range(len(PERSONAS))]
        q0_only_avg = round(sum(q0_only_scores) / len(q0_only_scores), 1)

        # With per-persona averaging, overall score should include Q1 data
        # (won't exactly equal Q0-only average unless all scores happen to be equal)
        all_q_scores = [
            ((i % 5) + 1 + ((i + 2) % 5) + 1) / 2  # avg of Q0 and Q1 per persona
            for i in range(len(PERSONAS))
        ]
        all_q_avg = round(sum(all_q_scores) / len(all_q_scores), 1)

        # The score should be all_q_avg (multi-question), not q0_only_avg
        assert abs(body["overall_score"] - all_q_avg) < 0.2, (
            f"overall_score {body['overall_score']} should be near multi-Q avg {all_q_avg}, "
            f"not Q0-only {q0_only_avg}"
        )
    finally:
        _delete_run(run_id)


@requires_real_llm
def test_bug3_enable_thinking_false_no_thinking_in_followup():
    """Bug 3: followup with enable_thinking=False should not stream thinking events or raw think tags."""
    run_id = f"e2e-bug3-{uuid.uuid4().hex[:8]}"
    _seed_multi_question_run(run_id, enable_thinking=0)
    try:
        # Get first persona from the seeded run
        conn = sqlite3.connect(HISTORY_DB)
        try:
            row = conn.execute(
                "SELECT DISTINCT persona_uuid FROM survey_answers WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            persona_uuid = row[0]
        finally:
            conn.close()

        # Stream a followup question and inspect the SSE event stream.
        thinking_chunks = []
        done_payload = None
        current_event = None
        current_data: list[str] = []
        with requests.post(
            f"{APP_BASE}/api/followup/ask",
            json={"run_id": run_id, "persona_uuid": persona_uuid, "question": "どのような点に最も魅力を感じますか？"},
            stream=True,
            timeout=60,
        ) as resp:
            assert resp.status_code == 200, resp.text
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    if current_event == "done" and current_data:
                        done_payload = json.loads("\n".join(current_data))
                    current_event = None
                    current_data = []
                    continue

                if line.startswith("event: "):
                    current_event = line[7:].strip()
                    if current_event == "thinking":
                        thinking_chunks.append(line)
                    continue

                if line.startswith("data: "):
                    current_data.append(line[6:])

            if current_event == "done" and current_data and done_payload is None:
                done_payload = json.loads("\n".join(current_data))

        assert len(thinking_chunks) == 0, (
            f"enable_thinking=False should produce no thinking SSE events, got {len(thinking_chunks)}"
        )
        assert done_payload is not None, "SSE stream should complete with done event"
        assert isinstance(done_payload.get("full_answer"), str)
        assert done_payload["full_answer"].strip(), "done payload should contain visible answer text"
        assert "<think>" not in done_payload["full_answer"], "raw <think> tags must not leak into final answer"
    finally:
        _delete_run(run_id)


@requires_real_llm
def test_bug3_enable_thinking_true_may_have_thinking_in_followup():
    """Bug 3: followup with enable_thinking=True can stream thinking events."""
    run_id = f"e2e-bug3-think-{uuid.uuid4().hex[:8]}"
    _seed_multi_question_run(run_id, enable_thinking=1)
    try:
        conn = sqlite3.connect(HISTORY_DB)
        try:
            row = conn.execute(
                "SELECT DISTINCT persona_uuid FROM survey_answers WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            persona_uuid = row[0]
        finally:
            conn.close()

        got_done = False
        with requests.post(
            f"{APP_BASE}/api/followup/ask",
            json={"run_id": run_id, "persona_uuid": persona_uuid, "question": "手数料についてどう思いますか？"},
            stream=True,
            timeout=90,
        ) as resp:
            assert resp.status_code == 200, resp.text
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("event: done"):
                        got_done = True
                        break

        assert got_done, "SSE stream should complete with done event"
    finally:
        _delete_run(run_id)
