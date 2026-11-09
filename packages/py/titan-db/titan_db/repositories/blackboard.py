"""Blackboard persistence helpers (M6.T2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.ids import uuid7
from titan_db.models.realtime import BlackboardEntry


class BlackboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_bb_version(self, session_id: uuid.UUID) -> int:
        row = await self._session.scalar(
            select(func.coalesce(func.max(BlackboardEntry.bb_version), 0)).where(
                BlackboardEntry.session_id == session_id
            )
        )
        return int(row or 0) + 1

    async def current_version(self, session_id: uuid.UUID, section: str, key: str) -> int | None:
        row = await self._session.scalar(
            select(BlackboardEntry.version)
            .where(
                BlackboardEntry.session_id == session_id,
                BlackboardEntry.section == section,
                BlackboardEntry.key == key,
            )
            .order_by(BlackboardEntry.version.desc())
            .limit(1)
        )
        return int(row) if row is not None else None

    async def latest_entry(self, session_id: uuid.UUID, section: str, key: str) -> BlackboardEntry | None:
        return await self._session.scalar(
            select(BlackboardEntry)
            .where(
                BlackboardEntry.session_id == session_id,
                BlackboardEntry.section == section,
                BlackboardEntry.key == key,
            )
            .order_by(BlackboardEntry.version.desc())
            .limit(1)
        )

    async def append(
        self,
        *,
        session_id: uuid.UUID,
        section: str,
        key: str,
        version: int,
        op: str,
        value: dict[str, Any] | None,
        author: str,
        confidence: float | None,
        evidence: list[Any],
        bb_version: int,
        message_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> BlackboardEntry:
        row = BlackboardEntry(
            id=uuid7(),
            session_id=session_id,
            section=section,
            key=key,
            version=version,
            op=op,
            value=value,
            author=author,
            confidence=confidence,
            evidence=evidence,
            message_id=message_id,
            bb_version=bb_version,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def snapshot(
        self,
        session_id: uuid.UUID,
        *,
        sections: list[str] | None = None,
        since_bb_version: int | None = None,
    ) -> tuple[int, list[BlackboardEntry]]:
        query = text(
            """
            SELECT id, session_id, section, key, version, op, value, author,
                   confidence, evidence, message_id, bb_version, expires_at, created_at
            FROM blackboard_current
            WHERE session_id = :session_id
              AND (:since IS NULL OR bb_version > :since)
            ORDER BY section, key
            """
        )
        result = await self._session.execute(query, {"session_id": session_id, "since": since_bb_version})
        entries: list[BlackboardEntry] = []
        for row in result.mappings():
            if sections is not None and row["section"] not in sections:
                continue
            entries.append(
                BlackboardEntry(
                    id=row["id"],
                    session_id=row["session_id"],
                    section=row["section"],
                    key=row["key"],
                    version=row["version"],
                    op=row["op"],
                    value=row["value"],
                    author=row["author"],
                    confidence=row["confidence"],
                    evidence=row["evidence"] or [],
                    message_id=row["message_id"],
                    bb_version=row["bb_version"],
                    expires_at=row["expires_at"],
                    created_at=row["created_at"],
                )
            )
        current = await self._session.scalar(
            select(func.coalesce(func.max(BlackboardEntry.bb_version), 0)).where(
                BlackboardEntry.session_id == session_id
            )
        )
        return int(current or 0), entries

    async def seed_version_counter(self, session_id: uuid.UUID, bb_version: int) -> None:
        """No-op placeholder: bb_version is derived from rows; kept for API symmetry."""
        del session_id, bb_version


async def upsert_bb_meta(session: AsyncSession, session_id: uuid.UUID, bb_version: int) -> None:
    """Reserved for future session metadata; entries already carry bb_version."""
    del session, session_id, bb_version


def entry_public(entry: BlackboardEntry) -> dict[str, Any]:
    return {
        "section": entry.section,
        "key": entry.key,
        "version": entry.version,
        "op": entry.op,
        "value": entry.value,
        "author": entry.author,
        "confidence": entry.confidence,
        "evidence": entry.evidence,
        "bb_version": entry.bb_version,
        "created_at": entry.created_at,
        "expires_at": entry.expires_at,
    }
