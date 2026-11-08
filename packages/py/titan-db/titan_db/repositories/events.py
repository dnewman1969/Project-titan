"""Persist game and system events from Redis streams (M2.T5)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.protocol.events import GameEvent
from titan_db.models.realtime import Event


class EventsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist_event(self, event: GameEvent) -> bool:
        row: dict[str, Any] = {
            "id": event.id,
            "session_id": event.session_id,
            "seq": event.seq,
            "type": event.type,
            "category": event.category,
            "severity": event.severity,
            "salience": event.salience,
            "source": event.source,
            "t_mono_ns": event.t_mono_ns,
            "t_session_ms": event.t_session_ms,
            "occurred_at": event.occurred_at,
            "payload": event.payload,
            "frame_seq": event.frame_seq,
        }
        stmt = insert(Event).values(**row).on_conflict_do_nothing(index_elements=["id"])
        result = await self._session.execute(stmt)
        return (result.rowcount or 0) == 1  # type: ignore[attr-defined]

    async def persist_events(self, events: list[GameEvent]) -> int:
        inserted = 0
        for event in events:
            if await self.persist_event(event):
                inserted += 1
        return inserted


def parse_event(data: str) -> GameEvent:
    return GameEvent.model_validate_json(data)
