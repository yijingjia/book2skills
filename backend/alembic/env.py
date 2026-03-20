"""Alembic migration environment — async mode (asyncpg).

Key design decisions:
- URL is read from app.core.config.settings to avoid hardcoding credentials.
- asyncpg is used as the driver (same as the FastAPI app), so we use
  run_sync() to bridge between SQLAlchemy's async engine and Alembic's
  synchronous migration runner.
- All ORM models are imported via app.models.models so autogenerate can
  detect schema changes automatically.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models.models  # noqa: F401  — registers all ORM models on Base
from alembic import context

# ---------------------------------------------------------------------------
# Project imports — must come before alembic config is read so that all
# mapped models are registered on Base.metadata.
# ---------------------------------------------------------------------------
from app.core.config import settings
from app.core.database import Base

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Set sqlalchemy.url programmatically from settings so credentials never
# appear in alembic.ini.
# asyncpg URL must use the "postgresql+asyncpg://" scheme.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up logging from the ini file if available.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline migrations (no live DB connection required — generates SQL scripts)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout rather than applying it directly, useful for
    generating migration scripts for DBAs to review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (connects to a live DB via asyncpg)
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync bridge."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
