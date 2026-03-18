import pandas as pd
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persona_store import PersonaStore


@pytest.fixture()
def store():
    """Build a PersonaStore from a small test DataFrame."""
    df = pd.DataFrame([
        {"uuid": "p1", "name": "田中太郎", "sex": "男", "age": 35, "region": "関東",
         "prefecture": "東京都", "occupation": "会社員", "education_level": "大学卒",
         "marital_status": "既婚", "persona": "ペルソナ1", "professional_persona": "会社員",
         "cultural_background": "日本", "skills_and_expertise": "営業",
         "hobbies_and_interests": "読書", "career_goals_and_ambitions": "昇進",
         "area": "都心", "country": "日本"},
        {"uuid": "p2", "name": "佐藤花子", "sex": "女", "age": 29, "region": "関東",
         "prefecture": "東京都", "occupation": "公務員", "education_level": "大学卒",
         "marital_status": "未婚", "persona": "ペルソナ2", "professional_persona": "公務員",
         "cultural_background": "日本", "skills_and_expertise": "事務",
         "hobbies_and_interests": "旅行", "career_goals_and_ambitions": "安定",
         "area": "都心", "country": "日本"},
        {"uuid": "p3", "name": "鈴木一郎", "sex": "男", "age": 52, "region": "関西",
         "prefecture": "大阪府", "occupation": "自営業", "education_level": "高校卒",
         "marital_status": "既婚", "persona": "ペルソナ3", "professional_persona": "自営業",
         "cultural_background": "日本", "skills_and_expertise": "経営",
         "hobbies_and_interests": "ゴルフ", "career_goals_and_ambitions": "事業拡大",
         "area": "都市部", "country": "日本"},
        {"uuid": "p4", "name": "高橋陽子", "sex": "女", "age": 45, "region": "関東",
         "prefecture": "神奈川県", "occupation": "会社員", "education_level": "大学卒",
         "marital_status": "既婚", "persona": "ペルソナ4", "professional_persona": "会社員",
         "cultural_background": "日本", "skills_and_expertise": "企画",
         "hobbies_and_interests": "料理", "career_goals_and_ambitions": "転職",
         "area": "郊外", "country": "日本"},
    ])
    return PersonaStore(df)


def test_total_count(store):
    assert store.total_count() == 4


def test_filters(store):
    f = store.get_filters()
    assert set(f["sex"]) == {"男", "女"}
    assert "関東" in f["regions"]
    assert "関西" in f["regions"]
    assert f["total_count"] == 4
    assert "大学卒" in f["education_levels"]
    assert "高校卒" in f["education_levels"]


def test_count_with_sex_filter(store):
    assert store.count(sex="男") == 2


def test_count_with_region_and_age(store):
    assert store.count(region="関東", age_min=30, age_max=50) == 2


def test_count_no_match(store):
    assert store.count(region="九州") == 0


def test_sample_returns_requested_count(store):
    total, sampled = store.sample(count=2)
    assert total == 4
    assert len(sampled) == 2


def test_sample_with_filter(store):
    total, sampled = store.sample(sex="男", count=10)
    assert total == 2
    assert len(sampled) == 2
    assert all(p["sex"] == "男" for p in sampled)


def test_sample_includes_all_persona_fields(store):
    _, sampled = store.sample(count=1)
    p = sampled[0]
    assert "uuid" in p
    assert "name" in p
    assert "persona" in p
    assert "occupation" in p


def test_get_persona_by_uuid(store):
    p = store.get_persona("p1")
    assert p is not None
    assert p["name"] == "田中太郎"
    assert p["uuid"] == "p1"


def test_get_persona_missing_returns_none(store):
    assert store.get_persona("nonexistent") is None


def test_occupation_filter_uses_partial_match(store):
    assert store.count(occupation="会社") == 2


def test_education_filter_uses_partial_match(store):
    assert store.count(education="大学") == 3


def test_financial_literacy_filter_missing_column_returns_empty(store, caplog):
    """When financial_literacy column is absent, return empty and emit a warning."""
    import logging
    with caplog.at_level(logging.WARNING, logger="persona_store"):
        result = store.count(financial_literacy="初心者")
    assert result == 0
    assert "financial_literacy column not found" in caplog.text
