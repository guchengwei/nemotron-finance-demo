import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persona_store import PersonaStore
from routers import personas


TEST_PERSONA_DATA = [
    {"uuid": "p1", "name": "田中太郎", "sex": "男", "age": 35, "region": "関東",
     "prefecture": "東京都", "occupation": "会社員", "education_level": "大学卒",
     "marital_status": "既婚", "persona": "ペルソナ1", "professional_persona": "会社員",
     "cultural_background": "日本", "skills_and_expertise": "営業",
     "skills_and_expertise_list": "['営業']", "hobbies_and_interests": "読書",
     "hobbies_and_interests_list": "['読書']", "career_goals_and_ambitions": "昇進",
     "area": "都心", "country": "日本",
     "financial_literacy": "中級者", "investment_experience": "あり",
     "financial_concerns": "老後資金", "annual_income_bracket": "600-800万円",
     "asset_bracket": "1000-3000万円", "primary_bank_type": "メガバンク"},
    {"uuid": "p2", "name": "佐藤花子", "sex": "女", "age": 29, "region": "関東",
     "prefecture": "東京都", "occupation": "公務員", "education_level": "大学卒",
     "marital_status": "未婚", "persona": "ペルソナ2", "professional_persona": "公務員",
     "cultural_background": "日本", "skills_and_expertise": "事務",
     "skills_and_expertise_list": "['事務']", "hobbies_and_interests": "旅行",
     "hobbies_and_interests_list": "['旅行']", "career_goals_and_ambitions": "安定",
     "area": "都心", "country": "日本",
     "financial_literacy": "初心者", "investment_experience": "なし",
     "financial_concerns": "生活費", "annual_income_bracket": "400-600万円",
     "asset_bracket": "500-1000万円", "primary_bank_type": "ネット銀行"},
    {"uuid": "p3", "name": "鈴木一郎", "sex": "男", "age": 52, "region": "関西",
     "prefecture": "大阪府", "occupation": "自営業", "education_level": "高校卒",
     "marital_status": "既婚", "persona": "ペルソナ3", "professional_persona": "自営業",
     "cultural_background": "日本", "skills_and_expertise": "経営",
     "skills_and_expertise_list": "['経営']", "hobbies_and_interests": "ゴルフ",
     "hobbies_and_interests_list": "['ゴルフ']", "career_goals_and_ambitions": "事業拡大",
     "area": "都市部", "country": "日本",
     "financial_literacy": "専門家", "investment_experience": "あり",
     "financial_concerns": "事業承継", "annual_income_bracket": "800万円以上",
     "asset_bracket": "3000万円以上", "primary_bank_type": "地方銀行"},
    {"uuid": "p4", "name": "高橋陽子", "sex": "女", "age": 45, "region": "関東",
     "prefecture": "神奈川県", "occupation": "会社員", "education_level": "大学卒",
     "marital_status": "既婚", "persona": "ペルソナ4", "professional_persona": "会社員",
     "cultural_background": "日本", "skills_and_expertise": "企画",
     "skills_and_expertise_list": "['企画']", "hobbies_and_interests": "料理",
     "hobbies_and_interests_list": "['料理']", "career_goals_and_ambitions": "転職",
     "area": "郊外", "country": "日本",
     "financial_literacy": "上級者", "investment_experience": "あり",
     "financial_concerns": "教育費", "annual_income_bracket": "600-800万円",
     "asset_bracket": "1000-3000万円", "primary_bank_type": "メガバンク"},
]


@pytest.fixture()
def test_store():
    """Create a PersonaStore from test data."""
    df = pd.DataFrame(TEST_PERSONA_DATA)
    return PersonaStore(df)


@pytest.fixture()
def client(test_store):
    """API client with PersonaStore patched in."""
    app = FastAPI()
    app.include_router(personas.router)

    with patch("routers.personas.get_store", return_value=test_store):
        with TestClient(app) as test_client:
            yield test_client
