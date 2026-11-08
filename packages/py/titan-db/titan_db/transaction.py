"""Explicit transaction helper for async repositories (M2.T2)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Commit on success, roll back on any exception."""
    if session.in_transaction():
        async with session.begin_nested():
            yield session
    else:
        async with session.begin():
            yield session


async def in_transaction[T](session: AsyncSession, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run `fn` inside a transaction (nested savepoint when one is already open)."""
    async with transaction(session):
        return await fn(session)


__all__ = ["in_transaction", "transaction"]
