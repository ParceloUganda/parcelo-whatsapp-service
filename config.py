"""Application configuration settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Centralised application configuration."""

    # Core environment
    environment: str = "development"
    log_level: str = "DEBUG"

    # External services
    openai_api_key: str
    supabase_url: str
    supabase_service_role_key: str
    luminous_api_url: str
    luminous_api_key: str

    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_notifications_enabled: bool = False

    # Phase 3 memory configuration
    llm_window_size: int = 12
    llm_max_prompt_tokens: int = 8000
    llm_output_buffer_tokens: int = 400
    summary_message_threshold: int = 5
    summary_max_input_tokens: int = 6000
    summary_max_output_tokens: int = 512
    embeddings_model: str = "text-embedding-3-small"
    embeddings_dimensions: int = 1536
    embeddings_chunk_size_tokens: int = 700
    embeddings_chunk_overlap_tokens: int = 140
    embeddings_max_chunks: int = 8
    embeddings_recall_limit: int = 5
    embeddings_min_similarity: float = 0.75
    enable_vector_recall: bool = True
    summary_refresh_minutes: int = 30

    # Phase 5 media handling
    enable_media_download: bool = False
    enable_vision_captions: bool = False
    enable_audio_transcription: bool = False
    media_storage_bucket: str = "chat-media"
    media_retention_days: int = 7
    media_cleanup_interval_minutes: int = 60
    vision_model: Optional[str] = None
    transcription_model: Optional[str] = None

    @field_validator("media_retention_days")
    @classmethod
    def _validate_retention(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MEDIA_RETENTION_DAYS must be greater than zero")
        return value

    @field_validator("media_cleanup_interval_minutes")
    @classmethod
    def _validate_cleanup_interval(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MEDIA_CLEANUP_INTERVAL_MINUTES must be greater than zero")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()  # type: ignore[call-arg]
