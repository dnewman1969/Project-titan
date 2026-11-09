"""Session lifecycle API (M6.T6)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

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


def test_kill_and_resume_release_live_session(api_client: TestClient, game_id: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_id": game_id,
            "title": "sticky",
            "settings": {"agents_enabled": False, "demo_telemetry": True},
        },
    )
    sid = created.json()["id"]
    assert (
        api_client.post(
            f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False}
        ).status_code
        == 202
    )

    assert api_client.post("/api/v1/safety/kill", headers=AUTH, json={"source": "hotkey"}).status_code == 200
    assert api_client.get(f"/api/v1/sessions/{sid}", headers=AUTH).json()["state"] == "ended"

    assert (
        api_client.post("/api/v1/safety/resume", headers=AUTH, json={"confirm": "RESUME"}).status_code == 200
    )
    fresh = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_id": game_id, "title": "after resume", "settings": {"agents_enabled": False}},
    )
    sid2 = fresh.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid2}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202, started.text


def test_start_supersedes_prior_live_session(api_client: TestClient, game_id: str) -> None:
    first = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_id": game_id,
            "title": "auto demo",
            "settings": {"agents_enabled": False, "demo_telemetry": True},
        },
    )
    assert first.status_code == 201
    sid_a = first.json()["id"]
    started_a = api_client.post(f"/api/v1/sessions/{sid_a}/start", headers=AUTH, json={"launch_game": False})
    assert started_a.status_code == 202
    assert started_a.json()["state"] == "live"

    second = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_id": game_id, "title": "real session", "settings": {"agents_enabled": False}},
    )
    assert second.status_code == 201
    sid_b = second.json()["id"]
    started_b = api_client.post(f"/api/v1/sessions/{sid_b}/start", headers=AUTH, json={"launch_game": False})
    assert started_b.status_code == 202, started_b.text
    assert started_b.json()["state"] == "live"
    got_a = api_client.get(f"/api/v1/sessions/{sid_a}", headers=AUTH)
    assert got_a.json()["state"] == "ended"
    assert got_a.json()["outcome"] == "aborted"


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


def test_session_start_uses_fixture_fallback(
    api_client: TestClient, game_slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    import titan_api.routers.sessions as sessions_routes

    replayed: list[object] = []

    async def fake_replay(session_id: object) -> None:
        replayed.append(session_id)

    monkeypatch.setattr(sessions_routes, "fixture_fallback_path", lambda slug: Path("/fixture.ndjson"))
    monkeypatch.setattr(sessions_routes, "start_demo_replay", fake_replay)
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_slug": game_slug, "title": "fallback", "settings": {"agents_enabled": False}},
    )
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    assert replayed


def test_session_start_play_enabled(
    api_client: TestClient, game_slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import titan_api.routers.sessions as sessions_routes

    flags = {"actions": False, "orch": False}

    class _Ctl:
        def start_orchestrator(self, session_id: UUID, **kwargs: object) -> None:
            flags["orch"] = True

        def start_actions(self, session_id: UUID, **kwargs: object) -> None:
            flags["actions"] = True

        def stop_orchestrator(self, session_id: UUID) -> None:
            return

        def stop_actions(self, session_id: UUID) -> None:
            return

    api_client.app.state.session_controller = _Ctl()

    async def noop(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(sessions_routes, "start_demo_replay", noop)
    monkeypatch.setattr(sessions_routes, "_seed_director_demo_line", noop)
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "play",
            "settings": {"agents_enabled": True, "play_enabled": True, "demo_telemetry": True},
        },
    )
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    assert flags["actions"] and flags["orch"]
