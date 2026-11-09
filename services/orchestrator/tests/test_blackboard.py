from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from titan_core.ids import uuid7
from titan_core.protocol.envelope import Address
from titan_db.models.games import Game
from titan_db.models.sessions import Session
from titan_db.seed import seed_all
from titan_orchestrator.blackboard import BlackboardService
from titan_orchestrator.errors import VersionMismatch
from titan_testing.db import TempDatabase

SID = UUID("0193f19c-0000-7000-8000-00000000aaaa")

pytestmark = pytest.mark.postgres


@pytest.mark.postgres
async def test_blackboard_cas_and_cache(
    migrated_db: TempDatabase, fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(migrated_db.url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        await seed_all(factory)
        game_id = await session.scalar(select(Game.id).limit(1))
        assert game_id is not None
        row = Session(
            id=SID,
            game_id=game_id,
            data_dir="titan-test-session",
            state="live",
            mode="observe",
        )
        session.add(row)
        await session.commit()

    async with factory() as session:
        bb = BlackboardService(SID, fake_redis, session, emit=None)
        entry = await bb.put(
            section="facts",
            key="fuel.stage",
            value={"ratio": 0.5},
            author=Address(kind="agent", id=str(uuid7()), role="flight_engineer"),
            expected_version=0,
            bb_write_sections=["facts"],
        )
        assert entry["version"] == 1
        cached = await bb.get("facts", "fuel.stage")
        assert cached is not None
        with pytest.raises(VersionMismatch):
            await bb.put(
                section="facts",
                key="fuel.stage",
                value={"ratio": 0.4},
                author=Address(kind="agent", id=str(uuid7()), role="flight_engineer"),
                expected_version=0,
                bb_write_sections=["facts"],
            )
    await engine.dispose()

