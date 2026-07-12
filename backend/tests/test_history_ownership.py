import fcntl

import pytest

import main
from config import settings


def test_second_backend_owner_fails_clearly(tmp_path):
    original = settings.history_db_path
    settings.history_db_path = str(tmp_path / "history.db")
    lock_path = f"{settings.history_db_path}.owner.lock"
    owner = open(lock_path, "a+")
    fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(RuntimeError, match="already owned by another backend"):
            main._acquire_history_lock()
    finally:
        fcntl.flock(owner.fileno(), fcntl.LOCK_UN)
        owner.close()
        main._release_history_lock()
        settings.history_db_path = original
