import os
from pathlib import Path
from unittest.mock import patch

import pytest


def test_settings_resolves_db_path_under_repo_data_dir():
    """db_path must resolve under the repo's data/ dir, not under backend/."""
    repo_root = Path(__file__).resolve().parents[2]
    expected_data_dir = repo_root / "data"

    # Clear env vars so defaults kick in
    env_clear = {k: "" for k in ("DB_PATH", "DATA_DIR", "HISTORY_DB_PATH")}
    with patch.dict(os.environ, env_clear, clear=False):
        import importlib
        import config as cfg
        original_settings = cfg.settings
        importlib.reload(cfg)
        resolved = Path(cfg.settings.db_path).resolve()
        cfg.settings = original_settings

    assert str(resolved).startswith(str(expected_data_dir)), (
        f"db_path {resolved} is not under {expected_data_dir}"
    )


def test_env_file_found_from_backend_cwd():
    """Settings must find .env even when CWD is backend/."""
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env"
    assert env_file.exists(), f".env not found at {env_file}"


def test_report_sampling_defaults():
    """report_temperature, report_repetition_penalty, report_frequency_penalty have correct defaults."""
    env_clear = {k: "" for k in ("REPORT_TEMPERATURE", "REPORT_REPETITION_PENALTY", "REPORT_FREQUENCY_PENALTY")}
    with patch.dict(os.environ, env_clear, clear=False):
        from config import Settings
        s = Settings()
    assert s.report_temperature == 0.1
    assert s.report_repetition_penalty == 1.15
    assert s.report_frequency_penalty == 0.3
