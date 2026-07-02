"""Application configuration, loaded from environment / .env via pydantic-settings.

Env var names are matched case-insensitively, so the uppercase names from the
project spec (LINEAR_API_KEY, DATABASE_URL, ...) map onto the lowercase fields below.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Secrets / external services ---
    linear_api_key: str = Field(default="")
    database_url: str = Field(default="")
    dashboard_auth_token: str = Field(default="")

    # Groq (OpenAI-compatible) powers the narrative digest. When unset the
    # digest degrades gracefully to a deterministic templated summary.
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    groq_api_url: str = Field(default="https://api.groq.com/openai/v1/chat/completions")

    # --- App behavior ---
    environment: str = Field(default="development")
    # TLS for the DB connection. Required by Neon (keep true in prod); set
    # DB_SSL=false for a local Postgres that has no TLS configured.
    db_ssl: bool = Field(default=True)
    # Comma-separated list accepted via env, e.g. CORS_ORIGINS="http://localhost:3000,https://app.example.com"
    cors_origins: str = Field(default="http://localhost:3000")
    linear_api_url: str = Field(default="https://api.linear.app/graphql")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def async_database_url(self) -> str:
        """Normalize a Neon/Postgres URL to the SQLAlchemy asyncpg driver.

        Neon hands out `postgresql://...`; SQLAlchemy async needs
        `postgresql+asyncpg://...`. We also strip libpq-only query params
        (e.g. `sslmode`, `channel_binding`) that asyncpg does not understand —
        TLS is configured on the engine instead (see app/db.py).
        """
        url = self.database_url
        if not url:
            return ""
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Drop query string; asyncpg rejects libpq params like sslmode.
        return url.split("?", 1)[0]

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (import-safe; reads .env once)."""
    return Settings()
