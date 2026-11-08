"""Alembic environment: async SQLAlchemy engine on asyncpg (Section 2.3, `titan-api`)."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from titan_core.config import load_config

config = context.config
url = config.get_main_option("sqlalchemy.url") or load_config().postgres.sqlalchemy_url("asyncpg")


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())
