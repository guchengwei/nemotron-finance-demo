import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


@pytest.fixture()
def app_client():
    """Client against the real app without lifespan (DB not initialized)."""
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


def test_health_returns_llm_reachable_field(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "mock_llm" in data
    assert "llm_reachable" in data


def test_ready_returns_503_when_db_not_loaded(app_client):
    main._db_ready.clear()
    resp = app_client.get("/ready")
    assert resp.status_code == 503
