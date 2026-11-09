"""Session lookups for the persister."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_db.models.sessions import Session


class SessionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._origins: dict[UUID, int | None] = {}

    async def clock_origin_mono_ns(self, session_id: UUID) -> int | None:
        if session_id not in self._origins:
            origin = await self._session.scalar(
                select(Session.clock_origin_mono_ns).where(Session.id == session_id)
            )
            self._origins[session_id] = origin
        return self._origins[session_id]

    async def t_session_ms(self, session_id: UUID, t_mono_ns: int) -> int:
        origin = await self.clock_origin_mono_ns(session_id)
        if origin is None:
            return 0
        return max(0, (t_mono_ns - origin) // 1_000_000)
