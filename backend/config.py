"""Application configuration loaded from environment variables."""

import json
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # LLM
    vllm_url: str = "http://localhost:8000/v1"
    vllm_model: str = "nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    mock_llm: bool = False
    llm_temperature: float = 0.7
    llm_max_tokens: int = 512
    report_max_tokens: int = 4096
    llm_concurrency: int = 4

    # Data paths
    data_dir: str = "./data"
    persona_parquet_path: str = "./data/personas.parquet"
    persona_hf_dataset: str = "nvidia/Nemotron-Personas-Japan"
    db_path: str = "./data/personas.db"
    history_db_path: str = "./data/history.db"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    frontend_port: int = 3000
    cors_origins: str = '["*"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.cors_origins)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
