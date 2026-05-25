"""Centralised settings loaded from environment variables.

All env vars share the `ALECA_` prefix and are case-insensitive.
Loaded once at process start; values are immutable.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Platform = Literal["pc", "xbox", "ps4", "switch"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALECA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # decrypt-agent (host-side service)
    agent_url: str = "http://host.docker.internal:8788"
    agent_token_path: str = "/wfm-token"
    agent_refresh_path: str = "/refresh"
    agent_toast_path: str = "/toast"

    # infra
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://aleca:aleca-local@rabbitmq:5672/"
    centrifugo_api: str = "http://centrifugo:8000/api"
    centrifugo_api_key: str = "change-me-in-env"
    centrifugo_token_hmac_secret: str = "change-me-in-env"
    centrifugo_token_ttl_seconds: int = 3600

    # filesystem
    data_dir: Path = Path("/data")
    sqlite_path: Path = Path("/data/wfm_history.db")
    aleca_data_home: Path | None = None  # set by agent on host, unset in container

    # behaviour
    ttl_seconds: int = 60
    log_level: str = "INFO"
    signal_throttle_seconds: int = 3600  # consumed by B.3 alert-rules engine (not B.2a)

    # warframe.market specifics
    wfm_base_url: str = "https://api.warframe.market/v1"
    wfm_platform: Platform = "pc"
    wfm_language: str = "en"
    wfm_rate_limit_per_second: int = 3

    # uvicorn-only (used by the `run()` entry point in main.py).
    # Default 127.0.0.1 is safe for local dev; the backend Dockerfile sets
    # ALECA_HOST=0.0.0.0 so the container exposes properly.
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor; use this everywhere except in tests that need reload."""
    return Settings()
