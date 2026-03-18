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
from routers import report


def _persona_json(uuid: str, name: str, age: int, sex: str, occupation: str, prefecture: str, literacy: str) -> str:
    return json.dumps(
        {
            "uuid": uuid,
            "name": name,
            "age": age,
            "sex": sex,
            "occupation": occupation,
            "prefecture": prefecture,
            "financial_literacy": literacy,
        },
        ensure_ascii=False,
    )


@pytest.fixture()
def report_client(tmp_path):
    history_db = str(tmp_path / "history.db")
    original_history_db = settings.history_db_path
    original_mock = settings.mock_llm
    settings.history_db_path = history_db
    settings.mock_llm = False

    _create_history_db()

    conn = sqlite3.connect(history_db)
    conn.execute(
        "INSERT INTO survey_runs (id, created_at, survey_theme, questions_json, filter_config_json, persona_count, status)"
        " VALUES (?, datetime('now'), ?, ?, '{}', 3, 'completed')",
        (
            "run-report",
            "AI家計管理アプリ",
            json.dumps(
                [
                    "このサービスへの関心度を教えてください",
                    "魅力を感じる点を教えてください",
                    "不安な点を教えてください",
                ],
                ensure_ascii=False,
            ),
        ),
    )

    answers = [
        (
            "run-report",
            "p1",
            "田中太郎、35歳、男性、会社員、東京都",
            _persona_json("p1", "田中太郎", 35, "男", "会社員", "東京都", "中級者"),
            0,
            "このサービスへの関心度を教えてください",
            "【評価: 5】家計の見える化が便利で、使いやすければすぐ試したいです。",
            5,
        ),
        (
            "run-report",
            "p1",
            "田中太郎、35歳、男性、会社員、東京都",
            _persona_json("p1", "田中太郎", 35, "男", "会社員", "東京都", "中級者"),
            1,
            "魅力を感じる点を教えてください",
            "日々の支出管理が自動化される点に期待しています。",
            None,
        ),
        (
            "run-report",
            "p2",
            "佐藤花子、29歳、女性、公務員、東京都",
            _persona_json("p2", "佐藤花子", 29, "女", "公務員", "東京都", "初心者"),
            0,
            "このサービスへの関心度を教えてください",
            "【評価: 2】便利そうですが、手数料やセキュリティが不安です。",
            2,
        ),
        (
            "run-report",
            "p2",
            "佐藤花子、29歳、女性、公務員、東京都",
            _persona_json("p2", "佐藤花子", 29, "女", "公務員", "東京都", "初心者"),
            2,
            "不安な点を教えてください",
            "設定が複雑だと続けられないと思います。",
            None,
        ),
        (
            "run-report",
            "p3",
            "鈴木一郎、52歳、男性、自営業、大阪府",
            _persona_json("p3", "鈴木一郎", 52, "男", "自営業", "大阪府", "専門家"),
            0,
            "このサービスへの関心度を教えてください",
            "【評価: 4】既存口座との連携が良ければ、事業資金管理にも応用できそうです。",
            4,
        ),
        (
            "run-report",
            "p3",
            "鈴木一郎、52歳、男性、自営業、大阪府",
            _persona_json("p3", "鈴木一郎", 52, "男", "自営業", "大阪府", "専門家"),
            1,
            "魅力を感じる点を教えてください",
            "事業と家計を横断して見られるなら独自性があります。",
            None,
        ),
    ]

    conn.executemany(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary, persona_full_json, question_index, question_text, answer, score)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        answers,
    )
    conn.commit()
    conn.close()

    app = FastAPI()
    app.include_router(report.router)
    with TestClient(app) as client:
        yield client, history_db

    settings.history_db_path = original_history_db
    settings.mock_llm = original_mock


def test_report_endpoint_uses_fallbacks_when_llm_returns_prose_only(report_client):
    client, history_db = report_client

    async def fake_raw(*args, **kwargs):
        return "全体として慎重な意見もありましたが、便利さへの期待もあります。"

    with patch("llm.generate_report_raw", side_effect=fake_raw):
        response = client.post("/api/report/generate", json={"run_id": "run-report"})

    assert response.status_code == 200
    body = response.json()
    assert body["group_tendency"]
    assert body["conclusion"]
    assert len(body["top_picks"]) == 3
    assert {pick["persona_uuid"] for pick in body["top_picks"]} <= {"p1", "p2", "p3"}

    cached = sqlite3.connect(history_db).execute(
        "SELECT report_json FROM survey_runs WHERE id = ?",
        ("run-report",),
    ).fetchone()[0]
    cached_json = json.loads(cached)
    assert cached_json == {key: value for key, value in body.items() if key != "run_id"}


def test_report_endpoint_preserves_partial_json_and_repairs_missing_fields(report_client):
    client, _ = report_client

    async def fake_raw(*args, **kwargs):
        return json.dumps(
            {
                "group_tendency": "若年層は期待と不安が混在しています。",
                "top_picks": [
                    {
                        "persona_uuid": "p1",
                        "highlight_reason": "前向きな期待が強い",
                    }
                ],
            },
            ensure_ascii=False,
        )

    with patch("llm.generate_report_raw", side_effect=fake_raw):
        response = client.post("/api/report/generate", json={"run_id": "run-report"})

    body = response.json()
    assert body["group_tendency"] == "若年層は期待と不安が混在しています。"
    assert body["conclusion"]
    assert len(body["top_picks"]) == 3
    first_pick = next(pick for pick in body["top_picks"] if pick["persona_uuid"] == "p1")
    assert first_pick["persona_name"] == "田中太郎"
    assert first_pick["persona_summary"]
    assert first_pick["highlight_quote"]


def test_report_endpoint_rejects_fabricated_top_pick_uuids(report_client):
    client, _ = report_client

    async def fake_raw(*args, **kwargs):
        return json.dumps(
            {
                "group_tendency": "全体では前向き寄りです。",
                "conclusion": "安全性説明を補強すると良いです。",
                "top_picks": [
                    {
                        "persona_uuid": "fake-uuid",
                        "persona_name": "架空",
                        "persona_summary": "架空",
                        "highlight_reason": "架空",
                        "highlight_quote": "架空",
                    },
                    {
                        "persona_uuid": "p2",
                        "persona_name": "佐藤花子",
                        "persona_summary": "佐藤花子、29歳、女性、公務員、東京都",
                        "highlight_reason": "懸念が具体的",
                        "highlight_quote": "手数料やセキュリティが不安です。",
                    },
                ],
            },
            ensure_ascii=False,
        )

    with patch("llm.generate_report_raw", side_effect=fake_raw):
        response = client.post("/api/report/generate", json={"run_id": "run-report"})

    body = response.json()
    assert len(body["top_picks"]) == 3
    assert {pick["persona_uuid"] for pick in body["top_picks"]} <= {"p1", "p2", "p3"}
    assert "fake-uuid" not in {pick["persona_uuid"] for pick in body["top_picks"]}
