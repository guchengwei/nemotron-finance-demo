import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from start_sh_restart import is_repo_owned_backend_cmdline


def test_matches_repo_owned_backend_cmdline():
    repo_dir = "/gen-ai/finance/nemotron-finance-demo"
    cmdline = (
        "python -m uvicorn main:app --host 0.0.0.0 --port 8080 "
        f"--env-file {repo_dir}/.env"
    )

    assert is_repo_owned_backend_cmdline(cmdline, repo_dir=repo_dir, port=8080)


def test_rejects_unrelated_listener_cmdline():
    repo_dir = "/gen-ai/finance/nemotron-finance-demo"
    cmdline = (
        "python -m uvicorn other:app --host 0.0.0.0 --port 8080 "
        "--env-file /tmp/other.env"
    )

    assert not is_repo_owned_backend_cmdline(cmdline, repo_dir=repo_dir, port=8080)
