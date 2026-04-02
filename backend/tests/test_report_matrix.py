import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.fixture
def mock_pipeline_events():
    """Yields a sequence of (event_type, event_data) tuples."""
    async def _pipeline(*args, **kwargs):
        yield ("axis_ready", {"x_axis": {"name": "関心度"}, "y_axis": {"name": "利用障壁"}, "quadrants": []})
        yield ("report_complete", {"total_scored": 0, "total_failed": 0})
    return _pipeline


@pytest.mark.asyncio
async def test_post_matrix_report_returns_sse(mock_pipeline_events):
    """POST /api/report/matrix returns text/event-stream content type."""
    with patch("routers.report_matrix.run_matrix_pipeline", mock_pipeline_events), \
         patch("routers.report_matrix.get_history_db") as mock_db:
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value={"id": "run-1", "survey_theme": "test", "questions_json": "[]"})
        mock_db.return_value.execute = AsyncMock(return_value=mock_cursor)
        mock_db.return_value.commit = AsyncMock()

        mock_answers_cursor = AsyncMock()
        mock_answers_cursor.fetchall = AsyncMock(return_value=[])
        mock_db.return_value.execute.side_effect = [mock_cursor, mock_answers_cursor, AsyncMock()]

        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/report/matrix",
                json={"survey_id": "run-1", "preset_key": "interest_barrier"})
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            assert "event: axis_ready" in resp.text


@pytest.mark.asyncio
async def test_get_matrix_report_404_when_missing():
    """GET /api/report/matrix/{id} returns 404 when no report exists."""
    with patch("routers.report_matrix.get_history_db") as mock_db:
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_db.return_value.execute = AsyncMock(return_value=mock_cursor)

        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/report/matrix/nonexistent-id")
            assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_matrix_report_returns_persisted_json():
    """GET /api/report/matrix/{id} returns persisted report data."""
    stored = json.dumps({"axes": {"x_axis": {"name": "関心度"}}})
    with patch("routers.report_matrix.get_history_db") as mock_db:
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value={"matrix_report_json": stored})
        mock_db.return_value.execute = AsyncMock(return_value=mock_cursor)

        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/report/matrix/run-1")
            assert resp.status_code == 200
            assert resp.json()["axes"]["x_axis"]["name"] == "関心度"


# -- New tests --

def test_full_name_extraction_from_persona_full_json():
    """Router should extract full name from persona_full_json.name."""
    from routers.report_matrix import _extract_full_name

    persona_json = json.dumps({"name": "太居 朔都", "age": 49})
    assert _extract_full_name(persona_json, "太居 朔都, 49歳男性, 建設業", "abc123") == "太居 朔都"


def test_full_name_fallback_to_summary():
    """When persona_full_json is None, extract from summary before first comma."""
    from routers.report_matrix import _extract_full_name

    assert _extract_full_name(None, "福井隆助, 40歳男性, 小売業", "abc123") == "福井隆助"


def test_full_name_fallback_to_uuid_prefix():
    """When both json and summary are empty, use UUID prefix."""
    from routers.report_matrix import _extract_full_name

    assert _extract_full_name(None, None, "abc12345-xyz") == "abc12345"


def test_projection_applied_to_scored_personas():
    """After projection, labels should come from the selected preset's quadrants."""
    from matrix_projection import spread_scores, assign_quadrant
    from matrix_models import AXIS_PRESETS

    preset = AXIS_PRESETS["interest_barrier"]

    # Simulate clustered raw scores (all y=4)
    raw_xs = [2.0, 3.0, 4.0, 4.0, 3.0]
    raw_ys = [4.0, 4.0, 3.0, 4.0, 4.0]

    spread_xs = spread_scores(raw_xs)
    spread_ys = spread_scores(raw_ys)

    # Verify spread happened
    assert min(spread_xs) < 2.0
    assert max(spread_xs) > 4.0

    # Verify quadrant labels are from the selected preset's canonical set
    canonical = {q.label for q in preset.quadrants}
    for sx, sy in zip(spread_xs, spread_ys):
        label = assign_quadrant(sx, sy, preset)
        assert label in canonical
