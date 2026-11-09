"""BlackboardService: Postgres history with Redis cache (M6.T2)."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.bus import bb_section_hash, bb_version_key, cache_entry_wire
from titan_core.protocol.common import Section
from titan_core.protocol.envelope import Address, Envelope, make_envelope
from titan_core.protocol.payloads import BBWritten, ConflictRaised
from titan_db.repositories.blackboard import BlackboardRepository, entry_public
from titan_db.transaction import transaction
from titan_orchestrator.errors import PermissionDenied, RateLimited, VersionMismatch

SECTION_WRITERS: dict[Section, frozenset[str]] = {
    "goals": frozenset({"director", "user"}),
    "plan": frozenset({"director"}),
    "tasks": frozenset({"system"}),
    "world_state": frozenset({"system"}),
    "facts": frozenset({"agent", "user"}),
    "hypotheses": frozenset({"agent"}),
    "risks": frozenset({"agent", "system"}),
    "discoveries": frozenset({"agent"}),
    # Crew writes lessons/notes as kind=agent (stored author "agent:…"), which is
    # what the desktop learn strip polls. director/system remain allowed.
    "lessons": frozenset({"director", "system", "agent"}),
    "notes": frozenset({"user", "agent"}),
}

DEFAULT_TTL_S: dict[Section, int | None] = {
    "facts": 600,
    "hypotheses": 300,
    "world_state": None,
}

Emit = Callable[[Envelope], Any]


class BlackboardService:
    def __init__(
        self,
        session_id: UUID,
        redis: aioredis.Redis,
        db: AsyncSession,
        *,
        emit: Emit | None = None,
        writes_per_minute: int = 20,
    ) -> None:
        self._session_id = session_id
        self._redis = redis
        self._db = db
        self._repo = BlackboardRepository(db)
        self._emit = emit
        self._writes_per_minute = writes_per_minute
        self._write_log: dict[str, list[int]] = defaultdict(list)

    async def get(self, section: Section, key: str) -> dict[str, Any] | None:
        cached = await self._redis.hget(bb_section_hash(self._session_id, section), key)
        if cached:
            payload = json.loads(cached)
            if payload.get("op") == "retract":
                return None
            return cast(dict[str, Any], payload)
        row = await self._repo.latest_entry(self._session_id, section, key)
        if row is None or row.op == "retract":
            return None
        return entry_public(row)

    async def snapshot(
        self, sections: list[Section] | None = None, *, since_bb_version: int | None = None
    ) -> tuple[int, list[dict[str, Any]]]:
        bb_version, rows = await self._repo.snapshot(
            self._session_id, sections=list(sections) if sections else None, since_bb_version=since_bb_version
        )
        return bb_version, [entry_public(row) for row in rows if row.op != "retract"]

    async def put(
        self,
        *,
        section: Section,
        key: str,
        value: dict[str, Any],
        author: Address | str,
        expected_version: int,
        confidence: float | None = 1.0,
        evidence: list[Any] | None = None,
        ttl_s: int | None = None,
        bb_write_sections: list[str] | None = None,
        message_id: UUID | None = None,
    ) -> dict[str, Any]:
        author_key = _author_key(author)
        self._check_rate(author_key)
        self._check_permission(section, author, author_key, expected_version, bb_write_sections, key)
        async with transaction(self._db):
            current = await self._repo.current_version(self._session_id, section, key)
            if expected_version == 0:
                if current is not None:
                    raise VersionMismatch(current)
                version = 1
            elif expected_version == -1:
                version = (current or 0) + 1
            else:
                if current != expected_version:
                    raise VersionMismatch(current)
                version = expected_version + 1
            ttl = ttl_s if ttl_s is not None else DEFAULT_TTL_S.get(section)
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl) if ttl is not None and ttl > 0 else None
            bb_version = await self._repo.next_bb_version(self._session_id)
            row = await self._repo.append(
                session_id=self._session_id,
                section=section,
                key=key,
                version=version,
                op="put",
                value=value,
                author=author_key,
                confidence=confidence,
                evidence=evidence or [],
                bb_version=bb_version,
                message_id=message_id,
                expires_at=expires_at,
            )
            await self._write_cache(section, key, row, expires_at)
            await self._emit_written(section, key, version, bb_version, "put")
            if section == "facts" and current is not None:
                await self._maybe_conflict(section, key, current, author_key, value)
        return entry_public(row)

    async def retract(
        self,
        *,
        section: Section,
        key: str,
        author: Address | str,
        expected_version: int,
        bb_write_sections: list[str] | None = None,
    ) -> dict[str, Any]:
        author_key = _author_key(author)
        self._check_rate(author_key)
        self._check_permission(section, author, author_key, expected_version, bb_write_sections, key)
        async with transaction(self._db):
            current = await self._repo.current_version(self._session_id, section, key)
            if current is None or current != expected_version:
                raise VersionMismatch(current)
            version = current + 1
            bb_version = await self._repo.next_bb_version(self._session_id)
            row = await self._repo.append(
                session_id=self._session_id,
                section=section,
                key=key,
                version=version,
                op="retract",
                value=None,
                author=author_key,
                confidence=None,
                evidence=[],
                bb_version=bb_version,
            )
            await self._write_cache(section, key, row, None)
            await self._emit_written(section, key, version, bb_version, "retract")
        return entry_public(row)

    async def rebuild_cache_from_db(self) -> int:
        """Rebuild Redis hashes from `blackboard_current` after orchestrator restart."""
        _, rows = await self._repo.snapshot(self._session_id)
        count = 0
        for row in rows:
            await self._write_cache(row.section, row.key, row, row.expires_at)
            count += 1
        if rows:
            await self._redis.set(bb_version_key(self._session_id), str(max(r.bb_version for r in rows)))
        return count

    def _check_rate(self, author: str) -> None:
        now = int(time.time())
        window = [stamp for stamp in self._write_log[author] if now - stamp < 60]
        self._write_log[author] = window
        if len(window) >= self._writes_per_minute:
            raise RateLimited
        self._write_log[author].append(now)

    def _check_permission(
        self,
        section: Section,
        author: Address | str,
        author_key: str,
        expected_version: int,
        bb_write_sections: list[str] | None,
        key: str,
    ) -> None:
        kind = author.kind if isinstance(author, Address) else author.split(":", 1)[0]
        allowed = SECTION_WRITERS.get(section, frozenset())
        if kind not in allowed and kind != "system":
            if section in (bb_write_sections or []):
                pass
            else:
                raise PermissionDenied
        if section == "world_state" and kind != "system":
            raise PermissionDenied
        if expected_version != -1 and kind == "agent" and section not in ("risks",):
            existing = None  # ownership enforced at call sites for MVP
            del existing, key

    async def _write_cache(self, section: str, key: str, row: Any, expires_at: datetime | None) -> None:
        wire = cache_entry_wire(
            version=row.version,
            value=row.value,
            author=row.author,
            confidence=row.confidence,
            evidence=row.evidence,
            op=row.op,
            expires_at=expires_at.isoformat() if expires_at else None,
        )
        await self._redis.hset(bb_section_hash(self._session_id, section), key, wire)
        await self._redis.set(bb_version_key(self._session_id), str(row.bb_version))

    async def _emit_written(self, section: str, key: str, version: int, bb_version: int, op: str) -> None:
        if self._emit is None:
            return
        section_lit = cast(Section, section)
        op_lit = cast(Literal["put", "retract"], op)
        payload = BBWritten(
            section=section_lit,
            key=key,
            version=version,
            op=op_lit,
            bb_version=bb_version,
        )
        envelope = make_envelope(
            type="bb.written",
            session_id=self._session_id,
            sender=Address(kind="system", id="system"),
            recipients=["broadcast"],
            visibility="internal",
            priority=3,
            payload=payload,
        )
        await self._emit(envelope)

    async def _maybe_conflict(
        self, section: Section, key: str, previous_version: int, author: str, value: Mapping[str, Any]
    ) -> None:
        previous = await self._repo.latest_entry(self._session_id, section, key)
        if previous is None or previous.version != previous_version:
            return
        if previous.author == author:
            return
        if previous.value == value:
            return
        if self._emit is None:
            return
        payload = ConflictRaised(
            section=section,
            key=key,
            versions=[previous.version, previous.version + 1],
            authors=[previous.author, author],
            summary="conflicting fact values",
        )
        envelope = make_envelope(
            type="conflict.raised",
            session_id=self._session_id,
            sender=Address(kind="system", id="system"),
            recipients=["director"],
            visibility="internal",
            priority=7,
            payload=payload,
        )
        await self._emit(envelope)


def _author_key(author: Address | str) -> str:
    if isinstance(author, str):
        return author
    if author.kind == "agent":
        return f"agent:{author.id}"
    if author.kind == "director":
        return "director"
    if author.kind == "user":
        return "user"
    return author.id
