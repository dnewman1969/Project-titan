"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.errors import ErrorCode, TitanError


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    if factory is None:
        raise TitanError(
            ErrorCode.DEPENDENCY_UNAVAILABLE, "Database is not configured.", dependency="postgres"
        )
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
