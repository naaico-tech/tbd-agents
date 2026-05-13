"""Alembic environment for async SQLAlchemy (asyncpg driver).

The database URL is resolved from the ``POSTGRES_URI`` environment variable,
falling back to the value configured in ``app/config.py``.  The ``alembic.ini``
``sqlalchemy.url`` key is intentionally left as a placeholder — this module
overrides it at runtime so the ini file never needs to contain real credentials.

We use raw-SQL DDL migrations (no ORM MetaData), so ``target_metadata = None``
and autogenerate is intentionally disabled.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# ---------------------------------------------------------------------------
# Alembic config object — provides access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No ORM MetaData — we drive migrations entirely with op.execute() raw SQL.
target_metadata = None


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


def get_url() -> str:
    """Return the async database URL.

    Priority:
    1. ``POSTGRES_URI`` environment variable (12-factor style)
    2. ``app.config.settings.postgres_uri`` (pydantic-settings / .env file)
    3. Hard-coded development default
    """
    env_url = os.environ.get("POSTGRES_URI")
    if env_url:
        return env_url
    try:
        from app.config import settings  # noqa: PLC0415

        return settings.postgres_uri
    except Exception:  # noqa: BLE001
        return "postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents"


# ---------------------------------------------------------------------------
# Offline mode — emits SQL to stdout without a live DB connection
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with a URL only; no DBAPI connection is required.
    Useful for generating a SQL script that can be reviewed before execution.
    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connects via AsyncEngine and runs migrations on the live DB
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """Synchronous inner function passed to ``connection.run_sync``."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an ``AsyncEngine`` and run migrations inside a connection."""
    engine = create_async_engine(get_url(), poolclass=pool.NullPool)

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """Entry-point for online mode — delegates to the async runner."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
