"""Application settings loaded from environment."""
from __future__ import annotations

import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    # Model used for the planner/synthesizer. Pick any Claude model you have access to.
    anthropic_model: str = "claude-opus-4-5"
    # Max tokens for the agent's final synthesis.
    max_tokens: int = 8000
    # Max web_search calls per itinerary request.
    max_web_searches: int = 6
    # SQLite by default for local dev. In production, point at a managed Postgres
    # (e.g. Neon) using `postgresql+asyncpg://user:pass@host/db`.
    database_url: str = "sqlite+aiosqlite:///./itinera.db"
    # Allowed CORS origins. Accepts either a JSON array (`["https://a", "https://b"]`)
    # or a comma-separated string (`https://a,https://b`) — the latter is friendlier
    # to set in dashboards like Render/Fly.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Global daily request quota for the /generate endpoints. Auto-resets at
    # 00:00 UTC. Set to 0 to disable rate limiting entirely.
    daily_request_limit: int = 7

    # Webhook to ping when the daily limit is hit. Discord, Slack, and ntfy.sh
    # URLs are auto-detected; anything else gets a generic JSON payload.
    # Leave unset to disable notifications.
    notify_webhook_url: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                # JSON-array form, e.g. ["http://a","http://b"]
                return json.loads(stripped)
            # Comma-separated form, friendlier for dashboard env vars.
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_postgres_scheme(cls, v: object) -> object:
        # Managed Postgres providers (Neon, Supabase, Railway) hand out URLs that
        # start with `postgres://` or `postgresql://`. SQLAlchemy's async engine
        # needs the explicit `postgresql+asyncpg://` driver — patch it transparently
        # so users can paste the connection string verbatim.
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return "postgresql+asyncpg://" + v[len("postgres://") :]
            if v.startswith("postgresql://") and "+asyncpg" not in v.split("://", 1)[0]:
                return "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v


settings = Settings()  # type: ignore[call-arg]
