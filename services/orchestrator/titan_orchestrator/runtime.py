"""SessionRuntime wiring for one live session (Section 2.11)."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_core.bus import SessionBus
from titan_core.clock import SessionClock
from titan_core.config import TitanConfig, load_config
from titan_core.streams import blocking_socket_timeout_s, redis_client
from titan_db.session import create_engine, create_session_factory
from titan_orchestrator.blackboard import BlackboardService
from titan_orchestrator.floor import FloorManager
from titan_orchestrator.router import AgentRegistration, MessageRouter
from titan_orchestrator.world_state import EventRouter


@dataclass
class SessionRuntime:
    session_id: UUID
    cfg: TitanConfig
    redis: aioredis.Redis
    sessions: async_sessionmaker[AsyncSession]
    clock: SessionClock
    bus: SessionBus
    router: MessageRouter = field(default_factory=MessageRouter)
    floor: FloorManager = field(default_factory=lambda: FloorManager(load_config().floor))
    event_router: EventRouter = field(default_factory=EventRouter)
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)
    _stopped: asyncio.Event = field(default_factory=asyncio.Event)

    @classmethod
    async def create(cls, session_id: UUID, cfg: TitanConfig | None = None) -> SessionRuntime:
        config = cfg or load_config()
        client = redis_client(config.redis, timeout_s=blocking_socket_timeout_s())
        engine = create_engine(config.postgres)
        factory = create_session_factory(engine)
        clock = SessionClock.start()
        runtime = cls(
            session_id=session_id,
            cfg=config,
            redis=client,
            sessions=factory,
            clock=clock,
            bus=SessionBus(client, session_id),
            floor=FloorManager(config.floor),
        )
        runtime.event_router.deliver = lambda iid, env: runtime.router.deliver(env)
        await runtime.bus.ensure_group()
        return runtime

    async def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._bus_loop(), name="bus"))

    async def stop(self) -> None:
        self._stopped.set()
        if self._tasks:
            await asyncio.wait(self._tasks, return_when=asyncio.ALL_COMPLETED)
            for task in self._tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._tasks.clear()
        await self.redis.aclose()

    async def register_team(self, roster: list[dict[str, Any]]) -> None:
        for item in roster:
            instance_id = UUID(str(item["instance_id"]))
            registration = AgentRegistration(
                instance_id=instance_id,
                role=str(item["role"]),
                persona_slug=str(item.get("persona_slug")) if item.get("persona_slug") else None,
                is_director=bool(item.get("is_director")),
            )
            self.router.register(registration)
            raw_patterns = item.get("event_subscriptions") or []
            patterns = [str(p) for p in raw_patterns] if isinstance(raw_patterns, list) else []
            if patterns:
                self.event_router.subscribe(instance_id, patterns)

    def blackboard_service(self, db: AsyncSession, *, emit: bool = True) -> BlackboardService:
        async def emit_envelope(envelope: Any) -> None:
            await self.bus.publish(envelope)

        return BlackboardService(
            self.session_id,
            self.redis,
            db,
            emit=emit_envelope if emit else None,
        )

    async def _bus_loop(self) -> None:
        last_id = "$"
        while not self._stopped.is_set():
            async for entry_id, envelope in self.bus.read_tail(last_id=last_id, block_ms=500):
                last_id = entry_id
                self.router.deliver(envelope)
            await asyncio.sleep(0)
