"""Session recording API (M8)."""

from __future__ import annotations

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from titan_api.auth import LAUNCH_TOKEN_ENV
from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_core.protocol.system import SupervisorStatus
from titan_db.models.games import Game
from titan_db.seed import seed_all
from titan_db.session import create_session_factory
from titan_testing.db import TempDatabase

TOKEN = "recordings-token"
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
    import asyncio

    from titan_db.session import create_engine

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


def _live_session(client: TestClient, game_slug: str) -> str:
    created = client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_slug": game_slug, "title": "record test", "settings": {"agents_enabled": False}},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    started = client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202, started.text
    return sid


def test_record_on_start_setting(api_client: TestClient, game_slug: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "auto rec",
            "settings": {"agents_enabled": False, "record_on_start": True},
        },
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    active = api_client.get(f"/api/v1/sessions/{sid}/recordings/active", headers=AUTH)
    assert active.status_code == 200
    item = active.json()["item"]
    assert item is not None
    assert item["state"] == "recording"


def test_recording_start_stop_without_obs(api_client: TestClient, game_slug: str) -> None:
    sid = _live_session(api_client, game_slug)
    empty = api_client.get(f"/api/v1/sessions/{sid}/recordings/active", headers=AUTH)
    assert empty.status_code == 200
    assert empty.json()["item"] is None

    started = api_client.post(f"/api/v1/sessions/{sid}/recordings/start", headers=AUTH)
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["state"] == "recording"
    assert body["manifest_path"]

    active = api_client.get(f"/api/v1/sessions/{sid}/recordings/active", headers=AUTH)
    assert active.status_code == 200
    assert active.json()["item"]["id"] == body["id"]

    stopped = api_client.post(f"/api/v1/sessions/{sid}/recordings/stop", headers=AUTH)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["state"] == "complete"
