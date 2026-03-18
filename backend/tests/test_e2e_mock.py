import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import _create_history_db
from persona_store import PersonaStore


@pytest.fixture()
def e2e_client(tmp_path):
    """Full app client with mock LLM and temp DBs."""
    history_db = str(tmp_path / "history.db")

    orig_hist = settings.history_db_path
    orig_mock = settings.mock_llm
    settings.history_db_path = history_db
    settings.mock_llm = True

    _create_history_db()

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

    import main
    main._db_ready.set()

    with patch("routers.personas.get_store", return_value=store), \
         patch("persona_store.get_store", return_value=store):
        with TestClient(main.app) as c:
            yield c

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
