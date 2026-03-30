import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from matrix_pipeline import run_matrix_pipeline


@pytest.fixture
def mock_survey_data():
    return {
        "survey_id": "test-run-1",
        "personas": [
            {"persona_id": "p1", "name": "田中", "industry": "小売業", "age": 40,
             "qa_text": "Q1: テスト回答1"},
            {"persona_id": "p2", "name": "佐藤", "industry": "建設業", "age": 35,
             "qa_text": "Q1: テスト回答2"},
        ],
    }


def _mock_score_result(persona_id, name, industry, age):
    return {"persona_id": persona_id, "name": name, "x_score": 3, "y_score": 3,
            "keywords": [], "quadrant_label": "慎重観察層", "industry": industry, "age": age}


@pytest.mark.asyncio
async def test_pipeline_event_sequence(mock_survey_data):
    mock_scorer = AsyncMock(side_effect=lambda pid, name, ind, age, qa, axes:
        _mock_score_result(pid, name, ind, age))

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.settings") as mock_settings:
        mock_settings.mock_llm = True
        mock_settings.llm_concurrency = 2

        events = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=mock_survey_data,
            preset_key="interest_barrier",
        ):
            events.append(event_type)

        assert events[0] == "axis_ready"
        scored_count = events.count("persona_scored")
        assert scored_count == 2
        assert "keywords_ready" in events
        assert events[-1] == "report_complete"


@pytest.mark.asyncio
async def test_pipeline_persona_error_does_not_abort(mock_survey_data):
    async def _score_side_effect(persona_id, name, industry, age, qa_text, axes):
        if persona_id == "p1":
            raise ValueError("LLM parse error")
        return _mock_score_result(persona_id, name, industry, age)

    mock_scorer = AsyncMock(side_effect=_score_side_effect)

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.llm_concurrency = 2

        events = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=mock_survey_data,
            preset_key="interest_barrier",
        ):
            events.append((event_type, event_data))

        event_types = [e[0] for e in events]
        assert "persona_score_error" in event_types
        assert "persona_scored" in event_types  # p2 still succeeded
        assert "report_complete" in event_types


@pytest.mark.asyncio
async def test_pipeline_invalid_preset():
    events = []
    async for event_type, event_data in run_matrix_pipeline(
        survey_data={"personas": [{"persona_id": "p1", "name": "x"}]},
        preset_key="nonexistent_preset",
    ):
        events.append((event_type, event_data))

    assert events[0][0] == "report_error"
    assert "Unknown preset" in events[0][1]["error"]


@pytest.mark.asyncio
async def test_pipeline_empty_personas():
    events = []
    async for event_type, event_data in run_matrix_pipeline(
        survey_data={"personas": []},
        preset_key="interest_barrier",
    ):
        events.append((event_type, event_data))

    event_types = [e[0] for e in events]
    assert "report_error" in event_types
