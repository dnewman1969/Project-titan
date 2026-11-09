from __future__ import annotations

import asyncio
from collections.abc import Iterator

import fakeredis
import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from titan_api.auth import LAUNCH_TOKEN_ENV
from titan_api.main import create_app
from titan_api.memory_ops import format_chroma_rows, format_query_hits
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


def test_memory_format_helpers() -> None:
    rows = format_chroma_rows(
        {"ids": ["a"], "documents": ["doc"], "metadatas": [{"game_slug": "ksp"}], "distances": [0.2]},
    )
    assert rows[0]["document"] == "doc"
    assert rows[0]["metadata"]["game_slug"] == "ksp"
    hits = format_query_hits(
        {
            "ids": [["a"]],
            "documents": [["d"]],
            "metadatas": [[{"kind": "lesson"}]],
            "distances": [[0.1]],
        },
    )
    assert hits[0]["distance"] == 0.1
    assert hits[0]["metadata"]["kind"] == "lesson"


@respx.mock
def test_session_start_seeds_prior_notes(api_client: TestClient, game_slug: str) -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-000000000011"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/query").mock(
        return_value=httpx.Response(
            200,
            json={"ids": [["m1"]], "documents": [["Brake before hills"]], "metadatas": [[{}]]},
        )
    )
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_slug": game_slug, "title": "prior-seed", "settings": {"agents_enabled": True, "play_enabled": False}},
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202, started.text
    board = api_client.get(f"/api/v1/sessions/{sid}/blackboard", headers=AUTH)
    assert board.status_code == 200
    keys = {row["key"] for row in board.json()["entries"] if row["section"] == "notes"}
    assert "prior.00" in keys
    assert "prior.seed" in keys


def test_memory_browse_and_write(api_client: TestClient) -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-0000000000dd"
    with respx.mock:
        respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
            return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
        )
        get_route = respx.post(
            f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/get"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "ids": ["m1"],
                    "documents": ["ascend gently"],
                    "metadatas": [{"game_slug": "ksp", "kind": "manual"}],
                },
            )
        )
        upsert = respx.post(
            f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/upsert"
        ).mock(return_value=httpx.Response(200, json={}))
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


@respx.mock
def test_memory_delete_items(api_client: TestClient) -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-0000000000ee"
    with respx.mock:
        respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
            return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
        )
        delete = respx.post(
            f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/delete"
        ).mock(return_value=httpx.Response(200, json={}))
        response = api_client.post(
            "/api/v1/memory/delete",
            headers=AUTH,
            json={"ids": ["manual:abc"]},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == 1
        assert delete.called
