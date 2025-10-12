"""Application configuration settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised application configuration."""

    # Core environment
    environment: str = "development"
    log_level: str = "INFO"

    # External services
    openai_api_key: str
    supabase_url: str
    supabase_service_role_key: str
    luminous_api_url: str
    luminous_api_key: str

    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_notifications_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()  # type: ignore[call-arg]
