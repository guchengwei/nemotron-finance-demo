"""Helpers for real browser E2E scenarios.

These hooks are only active when E2E_MODE=true so production behavior stays
unchanged.
"""

from fastapi import Request

from config import settings

E2E_SCENARIO_HEADER = "x-e2e-scenario"


def get_e2e_scenario(request: Request) -> str | None:
    """Return the active E2E scenario header when test hooks are enabled."""
    if not settings.e2e_mode:
        return None
    return request.headers.get(E2E_SCENARIO_HEADER)
