"""Seed a deterministic completed run for real-browser E2E tests.

Uses the live backend's sample endpoint to pick a real persona so the follow-up
chat still runs against actual local data and the real LLM.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.parse
import urllib.request
import uuid


SEED_LABEL = "E2E 深掘りシード"
SEED_RUN_ID = "e2e-followup-seed"
SEED_THEME = "オンライン資産運用アドバイザー導入前の顧客反応確認"
SEED_QUESTION = "このサービスを初めて知ったときの第一印象を教えてください。"


def _fetch_sampled_persona(backend_url: str) -> dict:
    url = f"{backend_url.rstrip('/')}/api/personas/sample?{urllib.parse.urlencode({'count': 1})}"
    with urllib.request.urlopen(url) as response:
        payload = json.loads(response.read().decode("utf-8"))
    sampled = payload.get("sampled") or []
    if not sampled:
        raise RuntimeError("No personas returned from sample endpoint")
    persona = dict(sampled[0])
    persona["persona"] = (
        (persona.get("persona") or "")
        + "\n\n"
        + "この人物は金融サービスの比較検討時に、費用、安心感、相談のしやすさを丁寧に見極める傾向があります。"
        * 12
    )
    return persona


def _persona_summary(persona: dict) -> str:
    sex = persona.get("sex") or ""
    sex_label = "男性" if sex == "男" else "女性" if sex == "女" else sex
    return (
        f"{persona.get('name', '不明')}, "
        f"{persona.get('age', '?')}歳{sex_label}, "
        f"{persona.get('occupation', '')}, "
        f"{persona.get('prefecture', '')}"
    )


def seed_history(backend_url: str, history_db_path: str) -> None:
    persona = _fetch_sampled_persona(backend_url)
    persona_summary = _persona_summary(persona)
    persona_json = json.dumps(persona, ensure_ascii=False)

    report = {
        "overall_score": 4.0,
        "score_distribution": {"1": 0, "2": 0, "3": 0, "4": 1, "5": 0},
        "group_tendency": "相談体験の安心感と手数料の透明性が評価の中心になっている。",
        "conclusion": "深掘りでは、導入時の不安要因と相談チャネルへの期待を確認する。",
        "top_picks": [
            {
                "persona_uuid": persona["uuid"],
                "persona_name": persona.get("name", "不明"),
                "persona_summary": persona_summary,
                "highlight_reason": "深掘りチャットの導線確認用に安定した代表回答者として選定。",
                "highlight_quote": "安心して相談できるなら、最初の一歩として試してみたいです。",
            }
        ],
        "demographic_breakdown": {
            "by_age": {"20-39": 4.0},
            "by_sex": {"男性" if persona.get("sex") == "男" else "女性": 4.0},
            "by_financial_literacy": {},
        },
    }

    conn = sqlite3.connect(history_db_path, timeout=30)
    try:
        conn.execute("DELETE FROM followup_chats WHERE run_id = ?", [SEED_RUN_ID])
        conn.execute("DELETE FROM survey_answers WHERE run_id = ?", [SEED_RUN_ID])
        conn.execute("DELETE FROM survey_runs WHERE id = ?", [SEED_RUN_ID])
        conn.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, persona_count, status, report_json, label) "
            "VALUES (?, ?, ?, ?, 'completed', ?, ?)",
            [
                SEED_RUN_ID,
                SEED_THEME,
                json.dumps([SEED_QUESTION], ensure_ascii=False),
                1,
                json.dumps(report, ensure_ascii=False),
                SEED_LABEL,
            ],
        )
        conn.execute(
            "INSERT INTO survey_answers "
            "(run_id, persona_uuid, persona_summary, persona_full_json, question_index, question_text, answer, score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                SEED_RUN_ID,
                persona["uuid"],
                persona_summary,
                persona_json,
                0,
                SEED_QUESTION,
                "【評価: 4】初回相談の安心感が高ければ前向きに試したいです。特に費用とサポート体制が明確なら利用を検討します。",
                4,
            ],
        )
        conn.commit()
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "run_id": SEED_RUN_ID,
                "label": SEED_LABEL,
                "persona_uuid": persona["uuid"],
                "persona_name": persona.get("name", "不明"),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--history-db", required=True)
    args = parser.parse_args()
    seed_history(args.backend_url, args.history_db)


if __name__ == "__main__":
    main()
