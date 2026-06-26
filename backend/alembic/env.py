"""Alembic environment — async, wired to the app's settings and metadata.

Connection config (driver, TLS) comes from app.db.build_async_engine so it
matches the running service exactly. Offline mode (`alembic upgrade --sql`)
uses the normalized async URL too.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection

import app.models  # noqa: E402,F401 — registers all tables on Base.metadata
from alembic import context

# Make `app` importable when Alembic runs from the backend/ directory.
from app.config import get_settings  # noqa: E402
from app.db import Base, build_async_engine  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    """Emit SQL without a live DB connection (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.async_database_url or "postgresql+asyncpg://localhost/placeholder",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = build_async_engine()
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
