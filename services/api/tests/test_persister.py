"""StreamPersister idempotency and start/stop (M2.T5)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator

import fakeredis
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_api.persister import StreamPersister
from titan_core.clock import utc_now
from titan_core.protocol.envelope import Address, make_envelope
from titan_core.protocol.events import GameEvent
from titan_core.streams import DATA_FIELD, session_bus_stream, session_events_stream
from titan_db.migrate import upgrade
from titan_db.models.realtime import AgentMessage, Event
from titan_db.repositories.events import EventsRepository
from titan_db.repositories.messages import MessagesRepository
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase, pg_server  # noqa: F401

pytestmark = pytest.mark.postgres


@pytest.fixture
def db_factory(pg_server, temp_db: TempDatabase) -> Iterator[async_sessionmaker[AsyncSession]]:  # noqa: F811
    upgrade(temp_db.url)
    engine = create_engine(temp_db.pg)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
async def session_row(temp_db: TempDatabase) -> uuid.UUID:
    conn = await temp_db.connect()
    try:
        sid = uuid.uuid4()
        gid = uuid.uuid4()
        await conn.execute(
            "INSERT INTO games (id, slug, name, adapter_id, adapter_version, domain, manifest) "
            "VALUES ($1, 'ksp', 'Kerbal', 'ksp', '1.0.0', 'space', '{}')",
            gid,
        )
        await conn.execute(
            "INSERT INTO sessions (id, game_id, state, mode, data_dir, clock_origin_mono_ns) "
            "VALUES ($1, $2, 'live', 'observe', '/tmp/s', 1_000_000)",
            sid,
            gid,
        )
        return sid
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_persister_start_stop_returns(db_factory: async_sessionmaker[AsyncSession]) -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    persister = StreamPersister(redis, db_factory, batch_interval_s=0.05, batch_max_rows=50)
    await persister.start()
    await asyncio.sleep(0.1)
    await persister.stop()


@pytest.mark.asyncio
async def test_persister_writes_bus_and_events(
    db_factory: async_sessionmaker[AsyncSession], session_row: uuid.UUID
) -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    bus = session_bus_stream(str(session_row))
    events = session_events_stream(str(session_row))
    envelope = make_envelope(
        type="chat.say",
        session_id=session_row,
        sender=Address(kind="agent", id=str(uuid.uuid4()), role="pilot"),
        recipients=["broadcast"],
        visibility="public",
        priority=5,
        payload={"text": "hello"},
    )
    game_event = GameEvent(
        id=uuid.uuid4(),
        session_id=session_row,
        seq=1,
        type="ksp.launch",
        category="game",
        severity="info",
        salience=0.8,
        source="adapter:ksp",
        t_mono_ns=envelope.t_mono_ns,
        t_session_ms=10,
        occurred_at=utc_now(),
        frame_seq=None,
        payload={"stage": 1},
    )
    await redis.xadd(bus, {DATA_FIELD: envelope.model_dump_json(by_alias=True)})
    await redis.xadd(events, {DATA_FIELD: game_event.model_dump_json()})
    persister = StreamPersister(redis, db_factory, batch_interval_s=0.05, batch_max_rows=50)
    await persister.flush_once()
    async with db_factory() as session:
        assert await session.scalar(select(func.count()).select_from(AgentMessage)) == 1
        assert await session.scalar(select(func.count()).select_from(Event)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicates", [2, 3, 5])
async def test_message_repository_idempotent(
    db_factory: async_sessionmaker[AsyncSession], session_row: uuid.UUID, duplicates: int
) -> None:
    envelope = make_envelope(
        type="chat.say",
        session_id=session_row,
        sender=Address(kind="agent", id=str(uuid.uuid4()), role="pilot"),
        recipients=["broadcast"],
        visibility="public",
        priority=5,
        payload={"text": "repeat"},
    )
    async with db_factory() as session:
        repo = MessagesRepository(session)
        for _ in range(duplicates):
            await repo.persist_envelope("1-0", envelope)
        await session.commit()
        total = await session.scalar(select(func.count()).select_from(AgentMessage))
        assert total == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicates", [2, 3, 5])
async def test_events_repository_idempotent(
    db_factory: async_sessionmaker[AsyncSession], session_row: uuid.UUID, duplicates: int
) -> None:
    event = GameEvent(
        id=uuid.uuid4(),
        session_id=session_row,
        seq=42,
        type="ksp.staging",
        category="game",
        severity="notice",
        salience=0.6,
        source="rule:ksp.stage",
        t_mono_ns=5_000_000,
        t_session_ms=20,
        occurred_at=utc_now(),
        frame_seq=10,
        payload={},
    )
    async with db_factory() as session:
        repo = EventsRepository(session)
        for _ in range(duplicates):
            await repo.persist_event(event)
        await session.commit()
        total = await session.scalar(select(func.count()).select_from(Event))
        assert total == 1
