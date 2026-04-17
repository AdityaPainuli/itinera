"""Application settings loaded from environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    # Model used for the planner/synthesizer. Pick any Claude model you have access to.
    anthropic_model: str = "claude-opus-4-5"
    # Max tokens for the agent's final synthesis.
    max_tokens: int = 8000
    # Max web_search calls per itinerary request.
    max_web_searches: int = 6
    # SQLite URL by default; swap to postgres+asyncpg://... in prod.
    database_url: str = "sqlite+aiosqlite:///./itinera.db"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()  # type: ignore[call-arg]
