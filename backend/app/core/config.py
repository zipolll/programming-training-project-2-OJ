"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

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
    database_path: Path = Path("data/runtime/oj.sqlite3")
    problems_path: Path = Path("data/problems")
    judge_temp_root: Path | None = None
    judge_compile_timeout_seconds: float = 10.0
    judge_compile_memory_limit_mb: int = 512
    judge_output_limit_bytes: int = 64 * 1024
    submission_code_limit: int = 1_000_000
    submission_result_limit_bytes: int = 64 * 1024
    submission_rate_limit_per_minute: int = 3
    evaluation_shutdown_timeout_seconds: float = 3.0
    session_cookie_name: str = "session_id"
    session_max_age_seconds: int = 7 * 24 * 60 * 60
    session_cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached immutable-by-convention settings object."""
    return Settings()
