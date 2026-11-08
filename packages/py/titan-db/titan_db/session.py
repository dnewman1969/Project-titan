"""Async SQLAlchemy engine and session factory (M2.T2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from titan_core.config import PostgresConfig


def create_engine(pg: PostgresConfig, *, pool_size: int = 5, max_overflow: int = 10) -> AsyncEngine:
    return create_async_engine(
        pg.sqlalchemy_url("asyncpg"),
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Open a session and close it when the block exits (no implicit transaction)."""
    async with factory() as session:
        yield session


__all__ = ["create_engine", "create_session_factory", "session_scope"]
