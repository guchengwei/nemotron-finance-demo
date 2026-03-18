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
        importlib.reload(cfg)
        resolved = Path(cfg.settings.db_path).resolve()

    assert str(resolved).startswith(str(expected_data_dir)), (
        f"db_path {resolved} is not under {expected_data_dir}"
    )


def test_env_file_found_from_backend_cwd():
    """Settings must find .env even when CWD is backend/."""
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env"
    assert env_file.exists(), f".env not found at {env_file}"
