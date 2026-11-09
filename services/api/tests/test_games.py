"""Games API routes (M4.T5)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import fakeredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase

TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def db_factory(migrated_db: TempDatabase) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(migrated_db.pg)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def games_client(
    migrated_db: TempDatabase, db_factory: async_sessionmaker[AsyncSession]
) -> Iterator[TestClient]:
    cfg = TitanConfig().model_copy(update={"postgres": migrated_db.pg})
    app = create_app(
        cfg,
        launch_token=TOKEN,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        session_factory=db_factory,
        start_persister=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_list_games_syncs_from_entry_points(games_client: TestClient) -> None:
    response = games_client.get("/api/v1/games", headers=AUTH)
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()["items"]}
    assert {"ksp", "ets2", "ats"}.issubset(slugs)

