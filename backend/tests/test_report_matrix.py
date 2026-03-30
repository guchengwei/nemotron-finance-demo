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
