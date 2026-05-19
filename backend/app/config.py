"""Application configuration via pydantic-settings (env-driven)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str = (
        "postgresql+asyncpg://riven:riven@localhost:5432/riven"
    )
    WARFRAME_API_BASE: str = "https://api.warframe.market/v1"
    WS_PATH: str = "/ws/alerts"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()
