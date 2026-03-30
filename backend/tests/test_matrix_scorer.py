import pytest
from matrix_scorer import parse_scoring_response


def test_parse_valid_json():
    raw = '{"x_score": 3, "y_score": 4, "keywords": [{"text": "手数料", "polarity": "strength"}], "quadrant_label": "様子見層"}'
    result = parse_scoring_response(raw)
    assert result["x_score"] == 3
    assert result["y_score"] == 4
    assert len(result["keywords"]) == 1


def test_parse_json_in_markdown_fence():
    raw = '```json\n{"x_score": 2, "y_score": 5, "keywords": [], "quadrant_label": "潜在採用層"}\n```'
    result = parse_scoring_response(raw)
    assert result["x_score"] == 2


def test_parse_malformed_returns_defaults():
    raw = "This is not JSON at all"
    result = parse_scoring_response(raw)
    assert result["x_score"] == 3  # midpoint default
    assert result["y_score"] == 3
    assert result["keywords"] == []


def test_parse_clamps_out_of_range_scores():
    raw = '{"x_score": 7, "y_score": -1, "keywords": [], "quadrant_label": ""}'
    result = parse_scoring_response(raw)
    assert result["x_score"] == 5
    assert result["y_score"] == 1


@pytest.mark.asyncio
async def test_score_persona_mock_mode():
    """score_persona returns valid scores with persona metadata in mock mode."""
    from unittest.mock import patch
    from matrix_scorer import score_persona
    from matrix_models import AXIS_PRESETS

    axes = AXIS_PRESETS["interest_barrier"]
    with patch("matrix_scorer.settings") as mock_settings:
        mock_settings.mock_llm = True
        result = await score_persona("p1", "田中", "小売業", 40, "Q1: テスト回答", axes)

    assert result["persona_id"] == "p1"
    assert result["name"] == "田中"
    assert result["industry"] == "小売業"
    assert result["age"] == 40
    assert 1 <= result["x_score"] <= 5
    assert 1 <= result["y_score"] <= 5
    assert isinstance(result["keywords"], list)
