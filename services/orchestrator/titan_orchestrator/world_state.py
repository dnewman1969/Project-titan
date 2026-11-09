"""WorldStateUpdater and EventRouter (M6.T7)."""

from __future__ import annotations

import fnmatch
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from titan_core.protocol.envelope import Address, Envelope, make_envelope
from titan_core.protocol.events import GameEvent
from titan_core.protocol.payloads import WorldStateTick
from titan_core.streams import DATA_FIELD, session_events_stream
from titan_orchestrator.blackboard import BlackboardService

Emit = Callable[[Envelope], Any]


@dataclass
class EventSubscription:
    instance_id: UUID
    patterns: list[str]


@dataclass
class EventRouter:
    subscriptions: list[EventSubscription] = field(default_factory=list)
    deliver: Callable[[UUID, Envelope], Any] | None = None

    def subscribe(self, instance_id: UUID, patterns: list[str]) -> None:
        self.subscriptions.append(EventSubscription(instance_id=instance_id, patterns=patterns))

    def route(self, event: GameEvent, session_id: UUID) -> list[Envelope]:
        envelopes: list[Envelope] = []
        for sub in self.subscriptions:
            if not any(fnmatch.fnmatch(event.type, pattern) for pattern in sub.patterns):
                continue
            envelope = make_envelope(
                type="game.event",
                session_id=session_id,
                sender=Address(kind="adapter", id=event.source),
                recipients=[f"instance:{sub.instance_id}"],
                visibility="internal",
                priority=5,
                payload=event,
            )
            envelopes.append(envelope)
            if self.deliver is not None:
                self.deliver(sub.instance_id, envelope)
        return envelopes


@dataclass
class WorldStateUpdater:
    session_id: UUID
    redis: aioredis.Redis
    blackboard: BlackboardService
    emit: Emit | None = None
    _last_write_s: float = 0.0

    async def ingest_telemetry(self, frame: dict[str, Any], *, scene: str = "live") -> bool:
        now = time.monotonic()
        if now - self._last_write_s < 1.0:
            return False
        self._last_write_s = now
        summary = frame.get("summary") or frame
        await self.blackboard.put(
            section="world_state",
            key="current",
            value={"scene": scene, "summary": summary},
            author=Address(kind="system", id="system"),
            expected_version=-1,
        )
        bb_version, _ = await self.blackboard.snapshot(sections=["world_state"])
        if self.emit is not None:
            payload = WorldStateTick(bb_version=bb_version, scene=scene, summary=summary)
            envelope = make_envelope(
                type="world.tick",
                session_id=self.session_id,
                sender=Address(kind="system", id="system"),
                recipients=["broadcast"],
                visibility="internal",
                priority=1,
                payload=payload,
            )
            await self.emit(envelope)
        return True

    async def poll_events_stream(self, last_id: str = "$") -> tuple[str, list[GameEvent]]:
        stream = session_events_stream(str(self.session_id))
        rows: Any = await self.redis.xread({stream: last_id}, count=16, block=1)
        events: list[GameEvent] = []
        next_id = last_id
        if not rows:
            return next_id, events
        for stream_name, entries in rows:
            if str(stream_name) != stream:
                continue
            for entry_id, fields in entries:
                next_id = str(entry_id)
                if not isinstance(fields, dict):
                    continue
                raw = fields.get(DATA_FIELD)
                if not isinstance(raw, str):
                    continue
                data = json.loads(raw)
                events.append(GameEvent.model_validate(data))
        return next_id, events
