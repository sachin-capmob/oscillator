"""Async SQLAlchemy engine & session management.

The engine is created lazily so the app (and `--help`/health checks) can boot
even before DATABASE_URL is configured. `Base` is the declarative base shared by
all ORM models and by Alembic (env.py imports it).
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def build_async_engine(echo: bool = False) -> AsyncEngine:
    """Construct an async engine from settings.

    Shared by the FastAPI app and Alembic so connection config (driver, TLS)
    stays in one place. Neon requires TLS (asyncpg takes an ssl.SSLContext,
    not a libpq `sslmode`); local dev Postgres typically has none — toggle
    with DB_SSL.
    """
    settings = get_settings()
    if not settings.database_configured:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and configure it."
        )
    # Pin every session to UTC so date_trunc / ::date bucketing is deterministic
    # and matches our UTC date anchoring (otherwise day boundaries shift by the
    # server/connection timezone and metrics land in the wrong bucket).
    connect_args: dict = {"server_settings": {"timezone": "UTC"}}
    if settings.db_ssl:
        connect_args["ssl"] = ssl.create_default_context()
    else:
        connect_args["ssl"] = False
    return create_async_engine(
        settings.async_database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_async_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
