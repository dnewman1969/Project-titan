"""Persist bus envelopes into `agent_messages` (M2.T5)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.protocol.envelope import Envelope
from titan_db.models.realtime import AgentMessage
from titan_db.repositories.sessions import SessionsRepository


class MessagesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sessions = SessionsRepository(session)

    async def persist_envelope(
        self, stream_seq: str, envelope: Envelope, *, t_session_ms: int | None = None
    ) -> bool:
        """Insert one row. Returns True when a new row was inserted."""
        ms = (
            t_session_ms
            if t_session_ms is not None
            else await self._sessions.t_session_ms(envelope.session_id, envelope.t_mono_ns)
        )
        sender = json.dumps(envelope.sender.model_dump(mode="json", by_alias=True))
        row: dict[str, Any] = {
            "id": envelope.id,
            "session_id": envelope.session_id,
            "stream_seq": stream_seq,
            "type": envelope.type,
            "sender": sender,
            "recipients": list(envelope.recipients),
            "correlation_id": envelope.correlation_id,
            "causation_id": envelope.causation_id,
            "visibility": envelope.visibility,
            "payload": envelope.payload,
            "t_session_ms": ms,
            "created_at": envelope.ts,
        }
        stmt = (
            insert(AgentMessage)
            .values(**row)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        result = await self._session.execute(stmt)
        return (result.rowcount or 0) == 1  # type: ignore[attr-defined]

    async def persist_envelopes(self, items: list[tuple[str, Envelope]]) -> int:
        inserted = 0
        for stream_seq, envelope in items:
            if await self.persist_envelope(stream_seq, envelope):
                inserted += 1
        return inserted


def parse_envelope(data: str, *, session_id: UUID | None = None) -> Envelope:
    envelope = Envelope.model_validate_json(data)
    if session_id is not None and envelope.session_id != session_id:
        raise ValueError("envelope session_id does not match stream session")
    return envelope
