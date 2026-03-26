"""Application configuration loaded from environment variables."""

import json
from pathlib import Path
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    # LLM
    vllm_url: str = "http://localhost:8000/v1"
    vllm_model: str = "nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    mock_llm: bool = False
    llm_temperature: float = 0.7
    llm_max_tokens: int = 512
    followup_max_tokens: int = 512
    followup_temperature: float = 0.7
    followup_max_history_messages: int = 20
    report_max_tokens: int = 4096
    report_temperature: float = 0.1
    report_repetition_penalty: float = 1.15
    report_frequency_penalty: float = 0.3
    llm_concurrency: int = 4

    # Data paths
    data_dir: str = "./data"
    persona_parquet_path: str = ""
    persona_hf_dataset: str = "nvidia/Nemotron-Personas-Japan"
    db_path: str = "./data/personas.db"
    history_db_path: str = "./data/history.db"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cors_origins: str = '["*"]'
    e2e_mode: bool = False

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.cors_origins)

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """Resolve relative paths against repo root, not CWD."""
        for field in ("data_dir", "db_path", "history_db_path", "persona_parquet_path"):
            val = getattr(self, field)
            if val:
                p = Path(val)
                if not p.is_absolute():
                    object.__setattr__(self, field, str(_REPO_ROOT / p))
        return self


settings = Settings()
