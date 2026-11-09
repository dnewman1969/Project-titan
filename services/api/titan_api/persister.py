"""Redis Streams to Postgres batch writer (M2.T5, Section 2.5)."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any, cast

import redis.asyncio as aioredis
import redis.exceptions
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_core.logging import get_logger
from titan_core.protocol.envelope import Envelope
from titan_core.protocol.events import GameEvent
from titan_core.streams import (
    BUS_TAIL,
    DATA_FIELD,
    EVENTS_TAIL,
    PERSIST_CONSUMER,
    PERSIST_GROUP,
    SESSION_STREAM_PREFIX,
    parse_session_stream,
)
from titan_db.repositories.events import EventsRepository, parse_event
from titan_db.repositories.messages import MessagesRepository, parse_envelope
from titan_db.transaction import transaction

log = get_logger(__name__)

BATCH_INTERVAL_S = 0.25
BATCH_MAX_ROWS = 500


@dataclass
class StreamPersister:
    redis: aioredis.Redis
    sessions: async_sessionmaker[AsyncSession]
    batch_interval_s: float = BATCH_INTERVAL_S
    batch_max_rows: int = BATCH_MAX_ROWS
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="stream-persister")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        task = self._task
        self._task = None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def flush_once(self) -> None:
        """Process one batch (used in tests and after API startup catch-up)."""
        streams = await self._discover_streams({})
        if streams:
            await self._read_batch(streams)

    async def _run(self) -> None:
        log.info("persister_started")
        streams: dict[str, str] = {}
        try:
            while not self._stop.is_set():
                try:
                    streams = await self._discover_streams(streams)
                    if streams:
                        await self._read_batch(streams)
                    else:
                        await asyncio.sleep(self.batch_interval_s)
                except (redis.exceptions.RedisError, OSError) as exc:
                    log.warning("persister_redis_error", error=type(exc).__name__)
                    await asyncio.sleep(1)
                if self._stop.is_set():
                    break
        finally:
            log.info("persister_stopped")

    async def _discover_streams(self, known: dict[str, str]) -> dict[str, str]:
        out = dict(known)
        cursor = 0
        pattern = f"{SESSION_STREAM_PREFIX}*{BUS_TAIL}"
        while True:
            cursor, keys = await self.redis.scan(cursor=cursor, match=pattern, count=200)
            for raw_key in keys:
                key = str(raw_key)
                session_id = parse_session_stream(key, tail=BUS_TAIL)
                if session_id is None:
                    continue
                bus = key
                events = f"{SESSION_STREAM_PREFIX}{session_id}{EVENTS_TAIL}"
                out[bus] = "bus"
                out[events] = "events"
                await self._ensure_group(bus)
                await self._ensure_group(events)
            if cursor == 0:
                break
        return out

    async def _ensure_group(self, stream: str) -> None:
        try:
            await self.redis.xgroup_create(stream, PERSIST_GROUP, id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _read_batch(self, streams: dict[str, str]) -> None:
        block_ms = max(1, int(self.batch_interval_s * 1000))
        read_from = {name: ">" for name in streams}
        try:
            reply = await asyncio.wait_for(
                self.redis.xreadgroup(
                    PERSIST_GROUP,
                    PERSIST_CONSUMER,
                    read_from,  # type: ignore[arg-type]
                    count=self.batch_max_rows,
                    block=block_ms,
                ),
                timeout=(block_ms / 1000.0) + 2.0,
            )
        except TimeoutError:
            return
        if not reply:
            return
        bus_items: list[tuple[str, Envelope]] = []
        event_items: list[GameEvent] = []
        ack_ids: dict[str, list[str]] = {}
        for stream_name, entries in cast(list[tuple[str, list[Any]]], reply):
            kind = streams.get(stream_name)
            for entry_id, fields in entries:
                ack_ids.setdefault(stream_name, []).append(str(entry_id))
                raw = _field_data(fields)
                if kind == "bus":
                    bus_items.append((str(entry_id), parse_envelope(raw)))
                elif kind == "events":
                    event_items.append(parse_event(raw))
        async with self.sessions() as session, transaction(session):
            msgs = MessagesRepository(session)
            evts = EventsRepository(session)
            await msgs.persist_envelopes(bus_items)
            await evts.persist_events(event_items)
        for stream_name, ids in ack_ids.items():
            if ids:
                await self.redis.xack(stream_name, PERSIST_GROUP, *ids)


def _field_data(fields: dict[str, str] | Any) -> str:
    value = fields.get(DATA_FIELD) if isinstance(fields, dict) else None
    if not isinstance(value, str):
        raise ValueError(f"stream entry missing {DATA_FIELD!r}")
    return value
