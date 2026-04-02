from types import SimpleNamespace

import pytest
from matrix_scorer import parse_scoring_response, _clamp_float


# -- Existing tests, updated for float return values --

def test_parse_valid_json():
    raw = '{"x_score": 3, "y_score": 4, "keywords": [{"text": "手数料", "polarity": "strength"}], "quadrant_label": "様子見層"}'
    result = parse_scoring_response(raw)
    assert result["x_score"] == 3.0
    assert result["y_score"] == 4.0
    assert isinstance(result["x_score"], float)
    assert isinstance(result["y_score"], float)
    assert len(result["keywords"]) == 1


def test_parse_json_in_markdown_fence():
    raw = '```json\n{"x_score": 2, "y_score": 5, "keywords": [], "quadrant_label": "潜在採用層"}\n```'
    result = parse_scoring_response(raw)
    assert result["x_score"] == 2.0


def test_parse_malformed_returns_defaults():
    raw = "This is not JSON at all"
    result = parse_scoring_response(raw)
    assert result["x_score"] == 3.0
    assert result["y_score"] == 3.0
    assert result["keywords"] == []


def test_parse_clamps_out_of_range_scores():
    raw = '{"x_score": 7, "y_score": -1, "keywords": [], "quadrant_label": ""}'
    result = parse_scoring_response(raw)
    assert result["x_score"] == 5.0
    assert result["y_score"] == 1.0


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
    assert 1.0 <= result["x_score"] <= 5.0
    assert 1.0 <= result["y_score"] <= 5.0
    assert isinstance(result["x_score"], float)
    assert isinstance(result["keywords"], list)


# -- New tests --

class TestClampFloat:
    def test_integer_stays(self):
        assert _clamp_float(3) == 3.0

    def test_float_stays(self):
        assert _clamp_float(3.5) == 3.5

    def test_rounds_to_half_up(self):
        assert _clamp_float(3.3) == 3.5

    def test_rounds_to_half_down(self):
        assert _clamp_float(3.7) == 3.5

    def test_rounds_to_whole(self):
        assert _clamp_float(3.8) == 4.0

    def test_boundary_0_75(self):
        assert _clamp_float(2.75) == 3.0

    def test_below_min(self):
        assert _clamp_float(0.2) == 1.0

    def test_above_max(self):
        assert _clamp_float(6.0) == 5.0

    def test_string_number(self):
        assert _clamp_float("4.5") == 4.5

    def test_invalid_returns_default(self):
        assert _clamp_float("abc") == 3.0

    def test_none_returns_default(self):
        assert _clamp_float(None) == 3.0


class TestParseQuadrantLabelDiscarded:
    def test_llm_quadrant_label_is_discarded(self):
        """quadrant_label from LLM is always discarded — computed deterministically later."""
        raw = '{"x_score": 4, "y_score": 2, "keywords": [], "quadrant_label": "即時採用層"}'
        result = parse_scoring_response(raw)
        assert result["quadrant_label"] == ""

    def test_missing_quadrant_label_is_empty(self):
        raw = '{"x_score": 4, "y_score": 2, "keywords": []}'
        result = parse_scoring_response(raw)
        assert result["quadrant_label"] == ""


class TestParseFloatScores:
    def test_float_scores_preserved(self):
        raw = '{"x_score": 4.5, "y_score": 2.5, "keywords": [], "quadrant_label": ""}'
        result = parse_scoring_response(raw)
        assert result["x_score"] == 4.5
        assert result["y_score"] == 2.5

    def test_integer_scores_become_float(self):
        raw = '{"x_score": 4, "y_score": 2, "keywords": [], "quadrant_label": ""}'
        result = parse_scoring_response(raw)
        assert isinstance(result["x_score"], float)
        assert isinstance(result["y_score"], float)


@pytest.mark.asyncio
async def test_score_persona_uses_preset_specific_y_axis_guidance():
    from matrix_models import AXIS_PRESETS
    from matrix_scorer import score_persona

    class _NoopAsyncContextManager:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeResponse:
        def __init__(self, content: str):
            self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]

    class _FakeCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return _FakeResponse(
                '{"x_score": 3, "y_score": 2, "keywords": [], "quadrant_label": ""}'
            )

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    fake_client = _FakeClient()
    axes = AXIS_PRESETS["risk_time"]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("matrix_scorer.get_client", lambda: fake_client)
        monkeypatch.setattr("matrix_scorer.get_semaphore", lambda: _NoopAsyncContextManager())
        monkeypatch.setattr(
            "matrix_scorer.settings",
            SimpleNamespace(
                mock_llm=False,
                vllm_model="mock-model",
                report_temperature=0,
                report_max_tokens=64,
            ),
        )

        await score_persona("p1", "田中", "小売業", 40, "Q1: テスト回答", axes)

    prompt = fake_client.chat.completions.calls[0]["messages"][0]["content"]
    assert "投資期間志向" in prompt
    assert "短期志向に近い回答は低スコア" in prompt
    assert "長期志向に近い回答は高スコア" in prompt
    assert "前向きで障壁が少ない場合は低スコア" not in prompt
