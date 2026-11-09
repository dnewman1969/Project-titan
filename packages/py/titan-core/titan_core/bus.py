"""Redis Streams bus client for session envelopes (Sections 2.5, 6.1 and 6.3)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from titan_core.protocol.envelope import ENVELOPE_SCHEMA, MAX_ENVELOPE_BYTES, Envelope
from titan_core.streams import DATA_FIELD, session_bus_stream, xadd_model

ORCH_GROUP = "orch"
ORCH_CONSUMER = "orch-1"
BUS_MAXLEN = 200_000


class EnvelopeValidationError(ValueError):
    """Raised when an envelope fails schema or size checks."""


def bb_section_hash(session_id: UUID | str, section: str) -> str:
    sid = str(session_id)
    return f"titan:s:{sid}:bb:{section}"


def bb_version_key(session_id: UUID | str) -> str:
    sid = str(session_id)
    return f"titan:s:{sid}:bb:version"


def validate_envelope_raw(data: str | bytes, *, session_id: UUID | None = None) -> Envelope:
    """Parse and validate a bus envelope; enforce the 32 KiB wire limit."""
    if isinstance(data, bytes):
        raw = data
        text = data.decode()
    else:
        text = data
        raw = text.encode()
    if len(raw) > MAX_ENVELOPE_BYTES:
        msg = f"envelope exceeds {MAX_ENVELOPE_BYTES} bytes"
        raise EnvelopeValidationError(msg)
    envelope = Envelope.model_validate_json(text)
    if envelope.schema_ != ENVELOPE_SCHEMA:
        msg = f"unsupported schema {envelope.schema_!r}"
        raise EnvelopeValidationError(msg)
    if session_id is not None and envelope.session_id != session_id:
        msg = "envelope session_id does not match bus session"
        raise EnvelopeValidationError(msg)
    return envelope


def validate_envelope(envelope: Envelope) -> Envelope:
    wire = envelope.model_dump_json(by_alias=True)
    if len(wire.encode()) > MAX_ENVELOPE_BYTES:
        msg = f"envelope exceeds {MAX_ENVELOPE_BYTES} bytes"
        raise EnvelopeValidationError(msg)
    return envelope


def envelope_expired(envelope: Envelope, *, now_ms: int | None = None) -> bool:
    if envelope.ttl_ms is None:
        return False
    import time

    now = int(time.time() * 1000) if now_ms is None else now_ms
    created = int(envelope.ts.timestamp() * 1000)
    return now - created > envelope.ttl_ms


class SessionBus:
    """Publishes to and reads from `titan:s:{sid}:bus`."""

    def __init__(self, client: aioredis.Redis, session_id: UUID) -> None:
        self._client = client
        self._session_id = session_id
        self._stream = session_bus_stream(str(session_id))

    @property
    def stream(self) -> str:
        return self._stream

    @property
    def session_id(self) -> UUID:
        return self._session_id

    async def publish(self, envelope: Envelope) -> str:
        validate_envelope(envelope)
        if envelope.session_id != self._session_id:
            msg = "envelope session_id does not match bus"
            raise EnvelopeValidationError(msg)
        return await xadd_model(self._client, self._stream, envelope, maxlen=BUS_MAXLEN)

    async def ensure_group(self, group: str = ORCH_GROUP) -> None:
        try:
            await self._client.xgroup_create(self._stream, group, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_group(
        self,
        group: str,
        consumer: str,
        *,
        count: int = 32,
        block_ms: int = 1000,
        last_id: str = ">",
    ) -> list[tuple[str, Envelope]]:
        rows: Any = await self._client.xreadgroup(
            group,
            consumer,
            {self._stream: last_id},
            count=count,
            block=block_ms if block_ms > 0 else None,
        )
        return _parse_xread(rows, session_id=self._session_id)

    async def ack(self, group: str, *entry_ids: str) -> int:
        if not entry_ids:
            return 0
        return int(await self._client.xack(self._stream, group, *entry_ids))

    async def read_tail(
        self, *, last_id: str = "$", count: int = 32, block_ms: int = 0
    ) -> AsyncIterator[tuple[str, Envelope]]:
        """Blocking tail read without a consumer group (used by the in-process router loop)."""
        cursor = last_id
        while True:
            rows: Any = await self._client.xread({self._stream: cursor}, count=count, block=block_ms or None)
            parsed = _parse_xread(rows, session_id=self._session_id)
            if not parsed:
                if block_ms <= 0:
                    break
                continue
            for entry_id, envelope in parsed:
                cursor = entry_id
                yield entry_id, envelope
            if block_ms <= 0:
                break


def _parse_xread(
    rows: list[tuple[str, list[tuple[str, Mapping[Any, Any]]]]] | list[Any],
    *,
    session_id: UUID,
) -> list[tuple[str, Envelope]]:
    out: list[tuple[str, Envelope]] = []
    for stream_name, entries in rows:
        if stream_name != session_bus_stream(str(session_id)):
            continue
        for entry_id, fields in entries:
            data = fields.get(DATA_FIELD) if fields else None
            if not isinstance(data, str):
                continue
            try:
                envelope = validate_envelope_raw(data, session_id=session_id)
            except EnvelopeValidationError:
                continue
            out.append((str(entry_id), envelope))
    return out


def cache_entry_wire(
    *,
    version: int,
    value: dict[str, Any] | None,
    author: str,
    confidence: float | None,
    evidence: list[Any],
    op: str,
    expires_at: str | None = None,
) -> str:
    return json.dumps(
        {
            "version": version,
            "value": value,
            "author": author,
            "confidence": confidence,
            "evidence": evidence,
            "op": op,
            "expires_at": expires_at,
        },
        separators=(",", ":"),
    )
