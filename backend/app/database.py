"""Database models and session setup."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlsplit, urlunsplit

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


def _gen_id() -> str:
    return uuid.uuid4().hex


class ItineraryRow(Base):
    __tablename__ = "itineraries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_gen_id)
    destination: Mapped[str] = mapped_column(String, index=True)
    duration_days: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(String)
    # Full serialized Itinerary (JSON). Cheap enough at our scale; index later if needed.
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RateLimitRow(Base):
    """Singleton row tracking the global daily request quota.

    There is only ever one row (id=1). `count` increments per generate attempt
    and auto-resets at the start of each UTC day. Manual reset / bump:

        UPDATE rate_limits SET count = 0, notified_at = NULL WHERE id = 1;
    """

    __tablename__ = "rate_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Set when we fire the "limit reached" notification, so we don't spam.
    # Cleared when the period rolls over.
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


def _build_engine_kwargs(url: str) -> tuple[str, dict]:
    """Translate provider-flavoured Postgres URLs into asyncpg-compatible ones.

    Neon/Supabase/Railway all hand out `?sslmode=require` in their connection
    strings, but asyncpg wants `ssl=require` passed via `connect_args` instead
    of the URL. Strip the query param and convert it so users can paste the
    raw provider URL into DATABASE_URL without surgery.
    """
    if not url.startswith("postgresql+asyncpg://"):
        return url, {}

    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    sslmode = query.pop("sslmode", [None])[0]

    new_query = "&".join(f"{k}={v[0]}" for k, v in query.items() if v)
    cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    connect_args: dict = {}
    if sslmode in {"require", "verify-ca", "verify-full"}:
        connect_args["ssl"] = True
    return cleaned, {"connect_args": connect_args} if connect_args else {}


_url, _engine_kwargs = _build_engine_kwargs(settings.database_url)
engine = create_async_engine(_url, echo=False, future=True, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    async with SessionLocal() as session:
        yield session
