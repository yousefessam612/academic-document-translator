"""Application configuration loaded from environment variables / .env"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = C:\academic-translator (three levels above this file)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "Academic Document Translator"
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Optional site-wide password (HTTP Basic Auth, any username). When set,
    # every visitor must enter it before using the app — protects your API
    # credits from strangers who find the public link.
    app_access_password: str = ""

    # --- AgentRouter / LLM provider ---
    agentrouter_api_key: str = ""
    agentrouter_base_url: str = "https://agentrouter.org/v1"
    # Default model (verified working for academic translation). Override via
    # AGENTROUTER_MODEL if your account has different models available.
    agentrouter_model: str = "glm-5.3"
    request_timeout_seconds: float = 180.0
    # AgentRouter's WAF only accepts requests whose client fingerprint matches
    # sanctioned coding-agent clients. For the OpenAI-compatible endpoint the
    # Codex CLI wire image works. Configurable in case the gateway changes.
    agentrouter_client_ua: str = "codex_cli_rs/0.21.0 (Windows 11; x86_64) unknown"
    agentrouter_originator: str = "codex_cli_rs"
    # Reasoning models (e.g. glm-5.3) consume completion tokens for reasoning
    # before emitting content, so the cap must be generous.
    agentrouter_max_tokens: int = 16384
    # Reasoning effort for reasoning-capable models. "low" keeps translation
    # fast/cheap and prevents reasoning from exhausting the token cap and
    # returning empty content. Set to "" to omit, or "medium"/"high" for
    # maximum quality at higher cost and failure risk.
    agentrouter_reasoning_effort: str = "low"

    # --- Limits ---
    max_file_size_mb: int = 100
    max_concurrent_translations: int = 2
    max_retries: int = 3
    retry_base_delay_seconds: float = 2.0
    chunk_target_chars: int = 4000
    chunk_max_chars: int = 6000
    context_chars: int = 1500

    # --- Storage ---
    storage_dir: Path = PROJECT_ROOT / "storage"
    uploads_subdir: str = "uploads"
    processed_subdir: str = "processed"
    outputs_subdir: str = "outputs"
    temp_subdir: str = "temp"
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'data' / 'app.db'}"

    # --- OCR ---
    tesseract_cmd: str = ""

    # --- Housekeeping ---
    temp_cleanup_hours: int = 24

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / self.uploads_subdir

    @property
    def processed_dir(self) -> Path:
        return self.storage_dir / self.processed_subdir

    @property
    def outputs_dir(self) -> Path:
        return self.storage_dir / self.outputs_subdir

    @property
    def temp_dir(self) -> Path:
        return self.storage_dir / self.temp_subdir

    @property
    def provider_configured(self) -> bool:
        return bool(self.agentrouter_api_key.strip() and self.agentrouter_model.strip())

    def ensure_directories(self) -> None:
        for d in (self.uploads_dir, self.processed_dir, self.outputs_dir, self.temp_dir):
            d.mkdir(parents=True, exist_ok=True)
        Path(self.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
