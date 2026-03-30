from matrix_keywords import aggregate_keywords
from matrix_models import ScoredPersona, KeywordEntry


def _make_persona(name, keywords):
    return ScoredPersona(
        persona_id=name, name=name, x_score=3, y_score=3,
        keywords=[KeywordEntry(text=t, polarity=p) for t, p in keywords],
    )


def test_aggregate_counts_and_groups():
    personas = [
        _make_persona("A", [("手数料", "strength"), ("不安", "weakness")]),
        _make_persona("B", [("手数料", "strength"), ("学習コスト", "weakness")]),
        _make_persona("C", [("手数料", "strength"), ("不安", "weakness"), ("24時間", "strength")]),
    ]
    result = aggregate_keywords(personas)
    assert result.strengths[0].text == "手数料"
    assert result.strengths[0].count == 3
    assert result.strengths[0].persona_names == ["A", "B", "C"]
    assert result.weaknesses[0].text == "不安"
    assert result.weaknesses[0].count == 2


def test_aggregate_empty():
    result = aggregate_keywords([])
    assert result.strengths == []
    assert result.weaknesses == []


def test_aggregate_top_k():
    personas = [
        _make_persona("A", [("kw1", "strength"), ("kw2", "strength"), ("kw3", "strength"),
                            ("kw4", "strength"), ("kw5", "strength"), ("kw6", "strength"),
                            ("kw7", "strength")]),
    ]
    result = aggregate_keywords(personas, top_k=5)
    assert len(result.strengths) <= 5
