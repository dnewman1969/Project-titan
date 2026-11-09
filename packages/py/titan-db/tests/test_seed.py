"""Dev database seed: games, personas, teams."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_db.migrate import upgrade
from titan_db.models.agents import Agent, AgentPersona, AgentTeam
from titan_db.models.games import Game
from titan_db.seed import seed_all
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


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_factory: async_sessionmaker[AsyncSession]) -> None:
    await seed_all(db_factory)
    await seed_all(db_factory)
    async with db_factory() as session:
        games = await session.scalar(select(func.count()).select_from(Game))
        personas = await session.scalar(select(func.count()).select_from(AgentPersona))
        teams = await session.scalar(select(func.count()).select_from(AgentTeam))
        agents = await session.scalar(select(func.count()).select_from(Agent))
        assert games == 3
        assert personas == 10
        assert teams == 3
        assert agents == 15
