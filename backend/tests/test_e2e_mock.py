import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import PERSONA_DDL, _create_history_db


@pytest.fixture()
def e2e_client(tmp_path):
    """Full app client with mock LLM and temp DBs."""
    persona_db = str(tmp_path / "personas.db")
    history_db = str(tmp_path / "history.db")

    conn = sqlite3.connect(persona_db)
    conn.executescript(PERSONA_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()

    orig_db = settings.db_path
    orig_hist = settings.history_db_path
    orig_mock = settings.mock_llm
    settings.db_path = persona_db
    settings.history_db_path = history_db
    settings.mock_llm = True

    _create_history_db()

    import main
    main._db_ready.set()

    with TestClient(main.app) as c:
        yield c

    settings.db_path = orig_db
    settings.history_db_path = orig_hist
    settings.mock_llm = orig_mock


def test_full_survey_flow_mock_mode(e2e_client):
    """The complete happy path: filters -> sample -> survey -> report."""
    # 1. Get filters
    resp = e2e_client.get("/api/personas/filters")
    assert resp.status_code == 200

    # 2. Sample personas
    resp = e2e_client.get("/api/personas/sample", params={"count": 1})
    assert resp.status_code == 200
    personas = resp.json()["sampled"]
    assert len(personas) >= 1
    pid = personas[0]["uuid"]

    # 3. Run survey (SSE)
    resp = e2e_client.post(
        "/api/survey/run",
        json={
            "persona_ids": [pid],
            "survey_theme": "テスト調査",
            "questions": ["この商品をどう思いますか？"],
        },
    )
    assert resp.status_code == 200
    text = resp.text
    assert "survey_complete" in text

    # Extract run_id from events
    run_id = None
    for line in text.split("\n"):
        if line.startswith("data: ") and "run_id" in line:
            data = json.loads(line[6:])
            if "run_id" in data:
                run_id = data["run_id"]
                break
    assert run_id is not None

    # 4. Generate report
    resp = e2e_client.post("/api/report/generate", json={"run_id": run_id})
    assert resp.status_code == 200
    report = resp.json()
    assert "overall_score" in report

    # 5. Check history
    resp = e2e_client.get("/api/history")
    assert resp.status_code == 200
    assert len(resp.json()["runs"]) >= 1
