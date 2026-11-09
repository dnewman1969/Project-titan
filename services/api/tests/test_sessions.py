"""Session lifecycle API (M6.T6)."""

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

TOKEN = "sessions-token"
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
def game_id(migrated_db: TempDatabase) -> str:
    import asyncio

    from titan_db.session import create_engine

    async def _load() -> str:
        engine = create_engine(migrated_db.pg)
        factory = create_session_factory(engine)
        await seed_all(factory)
        async with factory() as session:
            gid = await session.scalar(select(Game.id).limit(1))
        await engine.dispose()
        assert gid is not None
        return str(gid)

    return asyncio.run(_load())


def test_session_create_by_slug(api_client: TestClient, game_slug: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_slug": game_slug, "title": "slug path", "settings": {"agents_enabled": False}},
    )
    assert created.status_code == 201, created.text
    assert created.json()["state"] == "created"


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


def test_session_create_start_stop(api_client: TestClient, game_id: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_id": game_id, "title": "M6 integration", "settings": {"agents_enabled": False}},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    assert started.json()["state"] == "live"
    stopped = api_client.post(f"/api/v1/sessions/{sid}/stop", headers=AUTH, json={"outcome": "success"})
    assert stopped.status_code == 202
    assert stopped.json()["state"] == "ended"


def test_demo_session_seeds_director_note(
    api_client: TestClient, game_slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import titan_api.routers.sessions as sessions_routes

    async def noop_replay(_session_id: object) -> None:
        return None

    monkeypatch.setattr(sessions_routes, "start_demo_replay", noop_replay)
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "demo",
            "settings": {"agents_enabled": False, "demo_telemetry": True},
        },
    )
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    board = api_client.get(f"/api/v1/sessions/{sid}/blackboard", headers=AUTH)
    assert board.status_code == 200
    entries = board.json()["entries"]
    assert any(e.get("key") == "director.hello" for e in entries)


def test_session_start_invokes_live_telemetry(
    api_client: TestClient, game_slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import titan_api.routers.sessions as sessions_routes

    called: list[str] = []

    async def fake_live(session_id: object, *, game_slug: str, install_path: str) -> None:
        called.append(install_path)

    async def fake_profile(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(sessions_routes, "start_live_telemetry", fake_live)
    monkeypatch.setattr(sessions_routes, "start_demo_replay", fake_profile)
    monkeypatch.setattr(sessions_routes, "fixture_fallback_path", lambda slug: None)
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "live",
            "settings": {"agents_enabled": False},
        },
    )
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    assert not called  # no profile, no default, no fixture
