"""Application settings, loaded from environment variables (or a local .env file)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "dev"
    log_level: str = "INFO"

    # Compose maps the DB host port to 5433 to avoid clashing with a local Postgres.
    database_url: str = "postgresql+psycopg://drd:drd@localhost:5433/drd"
    test_database_url: str = "postgresql+psycopg://drd:drd@localhost:5433/drd_test"

    jwt_secret: str = "dev-only-insecure-secret-change-me-in-prod!"
    bcrypt_rounds: int = 12
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12

    # Comma-separated in the environment; exposed as a list below.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
