from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import UUID

import fakeredis
import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from titan_api.auth import LAUNCH_TOKEN_ENV
from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_core.protocol.system import SupervisorStatus
from titan_db.models.games import Game
from titan_db.seed import seed_all
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase

TOKEN = "memory-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.postgres


async def no_supervisor() -> SupervisorStatus | None:
    return None


@pytest.fixture
def api_client(migrated_db: TempDatabase, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, TOKEN)
    cfg = TitanConfig().model_copy(update={"postgres": migrated_db.pg})
    app = create_app(
        cfg,
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        start_persister=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def game_slug(migrated_db: TempDatabase) -> str:
    async def _load() -> str:
        engine = create_engine(migrated_db.pg)
        factory = create_session_factory(engine)
        await seed_all(factory)
        async with factory() as session:
            slug = await session.scalar(select(Game.slug).limit(1))
        await engine.dispose()
        assert slug is not None
        return slug

    return asyncio.run(_load())


def test_memory_browse_and_write(api_client: TestClient) -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-0000000000dd"
    with respx.mock:
        respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
            return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
        )
        get_route = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/get").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ids": ["m1"],
                    "documents": ["ascend gently"],
                    "metadatas": [{"game_slug": "ksp", "kind": "manual"}],
                },
            )
        )
        upsert = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/upsert").mock(
            return_value=httpx.Response(200, json={})
        )
        browse = api_client.get("/api/v1/memory/browse", headers=AUTH)
        assert browse.status_code == 200
        assert browse.json()["items"][0]["id"] == "m1"
        assert get_route.called

        written = api_client.post(
            "/api/v1/memory/items",
            headers=AUTH,
            json={"document": "Pitch to 45", "game_slug": "ksp"},
        )
        assert written.status_code == 200
        assert written.json()["written"] is True
        assert upsert.called
