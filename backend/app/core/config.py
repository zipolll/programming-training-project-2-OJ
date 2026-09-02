"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from OJ-prefixed environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OJ_",
        extra="ignore",
    )

    app_name: str = "Programming Training OJ"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8501"])


@lru_cache
def get_settings() -> Settings:
    """Return a cached immutable-by-convention settings object."""
    return Settings()
