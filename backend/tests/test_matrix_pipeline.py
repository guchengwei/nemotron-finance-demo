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


@pytest.mark.asyncio
async def test_pipeline_emits_recommendations_ready_in_real_llm_mode(mock_survey_data):
    """Bug 5: recommendations_ready must be emitted in non-mock mode."""
    mock_scorer = AsyncMock(side_effect=lambda pid, name, ind, age, qa, axes:
        _mock_score_result(pid, name, ind, age))

    mock_recs = [
        {"title": "テスト提案1", "body": "説明1", "tag": "教育"},
        {"title": "テスト提案2", "body": "説明2", "tag": "サービス"},
        {"title": "テスト提案3", "body": "説明3", "tag": "製品"},
    ]
    mock_gen_recs = AsyncMock(return_value=mock_recs)

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.generate_recommendations", mock_gen_recs), \
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
        assert "recommendations_ready" in event_types, \
            "recommendations_ready event must be emitted in real LLM mode"

        rec_events = [(t, d) for t, d in events if t == "recommendations_ready"]
        assert rec_events[0][1] == mock_recs, \
            "recommendations_ready data must match the generate_recommendations return value"


@pytest.mark.asyncio
async def test_pipeline_recommendations_fallback_on_error(mock_survey_data):
    """If recommendation generation fails, emit empty list instead of crashing."""
    mock_scorer = AsyncMock(side_effect=lambda pid, name, ind, age, qa, axes:
        _mock_score_result(pid, name, ind, age))

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.settings") as mock_settings, \
         patch("matrix_pipeline.generate_recommendations",
               side_effect=Exception("LLM down")):
        mock_settings.mock_llm = False
        mock_settings.llm_concurrency = 2

        events = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=mock_survey_data,
            preset_key="interest_barrier",
        ):
            events.append((event_type, event_data))

        rec_events = [(t, d) for t, d in events if t == "recommendations_ready"]
        assert len(rec_events) == 1, "Should emit recommendations_ready even on error"
        assert rec_events[0][1] == [], "Should emit empty list on failure"


@pytest.mark.asyncio
async def test_pipeline_emits_keyword_elaborated_events(mock_survey_data):
    """After keywords_ready, pipeline should emit keyword_elaborated events."""
    mock_scorer = AsyncMock(side_effect=lambda pid, name, ind, age, qa, axes:
        {**_mock_score_result(pid, name, ind, age),
         "keywords": [{"text": "手数料の安さ", "polarity": "strength"}]})

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.settings") as mock_settings:
        mock_settings.mock_llm = True
        mock_settings.llm_concurrency = 2

        events = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=mock_survey_data,
            preset_key="interest_barrier",
        ):
            events.append((event_type, event_data))

        event_types = [e[0] for e in events]
        kw_idx = event_types.index("keywords_ready")
        # keyword_elaborated events should appear after keywords_ready
        post_kw_events = event_types[kw_idx+1:]
        assert "keyword_elaborated" in post_kw_events, \
            "Should emit keyword_elaborated events after keywords_ready"


@pytest.mark.asyncio
async def test_pipeline_emits_keyword_elaborated_in_real_llm_mode(mock_survey_data):
    """keyword_elaborated must be emitted in real-LLM mode too."""
    mock_scorer = AsyncMock(side_effect=lambda pid, name, ind, age, qa, axes:
        {**_mock_score_result(pid, name, ind, age),
         "keywords": [{"text": "手数料の安さ", "polarity": "strength"}]})

    mock_elaborations = {"手数料の安さ": "コスト競争力の高さが評価されています。"}

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.settings") as mock_settings, \
         patch("matrix_pipeline.elaborate_keywords",
               new=AsyncMock(return_value=mock_elaborations)):
        mock_settings.mock_llm = False
        mock_settings.llm_concurrency = 2

        events = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=mock_survey_data,
            preset_key="interest_barrier",
        ):
            events.append((event_type, event_data))

    event_types = [e[0] for e in events]
    kw_idx = event_types.index("keywords_ready")
    post_kw = event_types[kw_idx + 1:]
    assert "keyword_elaborated" in post_kw, \
        "keyword_elaborated must be emitted after keywords_ready in real-LLM mode"

    elab_events = [(t, d) for t, d in events if t == "keyword_elaborated"]
    assert len(elab_events) >= 1
    assert elab_events[0][1]["keyword_text"] == "手数料の安さ"
    assert elab_events[0][1]["elaboration"] == "コスト競争力の高さが評価されています。"


@pytest.mark.asyncio
async def test_pipeline_emits_preset_specific_quadrant_labels_for_risk_time():
    """All four quadrant positions should be reachable for a non-default preset (risk_time)."""

    survey_data = {
        "survey_id": "test-run-risk-time-4q",
        "personas": [
            {"persona_id": "p1", "name": "田中", "industry": "小売業", "age": 40, "qa_text": "Q1: テスト回答1"},
            {"persona_id": "p2", "name": "佐藤", "industry": "建設業", "age": 35, "qa_text": "Q1: テスト回答2"},
            {"persona_id": "p3", "name": "鈴木", "industry": "製造業", "age": 50, "qa_text": "Q1: テスト回答3"},
            {"persona_id": "p4", "name": "高橋", "industry": "金融業", "age": 45, "qa_text": "Q1: テスト回答4"},
        ],
    }

    async def _score_side_effect(persona_id, name, industry, age, qa_text, axes):
        # With 4 distinct values, projection maps to ~[1.0, 2.3, 3.7, 5.0] per axis.
        # We pick raw ranks so that after independent x/y projection we hit all 4 quadrants.
        raw_by_id = {
            "p1": (1.0, 1.0),  # low x, low y -> bottom-left
            "p2": (2.0, 5.0),  # low x, high y -> top-left
            "p3": (4.0, 2.0),  # high x, low y -> bottom-right
            "p4": (5.0, 4.0),  # high x, high y -> top-right
        }
        x_score, y_score = raw_by_id[persona_id]
        return {
            "persona_id": persona_id,
            "name": name,
            "x_score": x_score,
            "y_score": y_score,
            "keywords": [],
            "quadrant_label": "",
            "industry": industry,
            "age": age,
        }

    mock_scorer = AsyncMock(side_effect=_score_side_effect)

    with patch("matrix_pipeline.score_persona", mock_scorer), patch(
        "matrix_pipeline.settings"
    ) as mock_settings:
        mock_settings.mock_llm = True
        mock_settings.llm_concurrency = 4

        labels = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=survey_data,
            preset_key="risk_time",
        ):
            if event_type == "persona_scored":
                labels.append(event_data["quadrant_label"])

    assert set(labels) == {"堅実長期層", "積極投資層", "現金保守層", "機動投機層"}


@pytest.mark.asyncio
async def test_pipeline_unknown_keyword_gets_empty_elaboration(mock_survey_data):
    """Keywords not in MOCK_ELABORATIONS should get empty elaboration, not placeholder."""
    mock_scorer = AsyncMock(side_effect=lambda pid, name, ind, age, qa, axes:
        {**_mock_score_result(pid, name, ind, age),
         "keywords": [{"text": "未知キーワード", "polarity": "strength"}]})

    with patch("matrix_pipeline.score_persona", mock_scorer), \
         patch("matrix_pipeline.settings") as mock_settings:
        mock_settings.mock_llm = True
        mock_settings.llm_concurrency = 2

        events = []
        async for event_type, event_data in run_matrix_pipeline(
            survey_data=mock_survey_data,
            preset_key="interest_barrier",
        ):
            events.append((event_type, event_data))

        elab_events = [(t, d) for t, d in events if t == "keyword_elaborated"]
        unknown_elab = [e for e in elab_events if e[1]["keyword_text"] == "未知キーワード"]
        assert len(unknown_elab) == 1
        assert unknown_elab[0][1]["elaboration"] == "", \
            "Unknown keywords should get empty elaboration, not default placeholder"
