"""Session lifecycle API (M6.T6)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
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
    # Keep attach waits short in unit tests; HIL uses the real post-launch deadline.
    monkeypatch.setenv("TITAN_PLAY_ATTACH_WAIT_S", "0.2")
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


@respx.mock
def test_session_stop_persists_learnings(
    api_client: TestClient, game_id: str, migrated_db: TempDatabase
) -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-0000000000cc"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    upsert = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/upsert").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/query").mock(
        return_value=httpx.Response(200, json={"ids": [[]], "documents": [[]], "metadatas": [[]]})
    )

    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_id": game_id, "title": "memory-persist", "settings": {"agents_enabled": False}},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202, started.text

    import asyncio

    from titan_db.repositories.blackboard import BlackboardRepository
    from titan_db.session import create_engine

    async def _seed() -> None:
        engine = create_engine(migrated_db.pg)
        factory = create_session_factory(engine)
        async with factory() as db:
            bb = BlackboardRepository(db)
            bb_version = await bb.next_bb_version(UUID(sid))
            await bb.append(
                session_id=UUID(sid),
                section="discoveries",
                key="event.00001",
                version=1,
                op="put",
                value={"text": "Fuel margins tight on ascent"},
                author="agent:fe",
                confidence=0.85,
                evidence=[],
                bb_version=bb_version,
            )
            await db.commit()
        await engine.dispose()

    asyncio.run(_seed())

    stopped = api_client.post(f"/api/v1/sessions/{sid}/stop", headers=AUTH, json={"outcome": "success"})
    assert stopped.status_code == 202, stopped.text
    assert stopped.json().get("memory_persist", {}).get("written", 0) >= 1
    assert upsert.called


def test_session_create_start_stop(api_client: TestClient, game_id: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_id": game_id, "title": "M6 integration", "settings": {"agents_enabled": False}},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    # Eager commit on create: GET must see the row before /start (Windows HIL race).
    got = api_client.get(f"/api/v1/sessions/{sid}", headers=AUTH)
    assert got.status_code == 200, got.text
    assert got.json()["state"] == "created"
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202
    assert started.json()["state"] == "live"
    stopped = api_client.post(f"/api/v1/sessions/{sid}/stop", headers=AUTH, json={"outcome": "success"})
    assert stopped.status_code == 202
    assert stopped.json()["state"] == "ended"


def test_session_auto_start_atomic(api_client: TestClient, game_id: str) -> None:
    """New Session dialog path: one POST creates and starts (no follow-up /start)."""
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_id": game_id,
            "title": "atomic start",
            "auto_start": True,
            "launch_game": False,
            "settings": {"agents_enabled": False, "demo_telemetry": True},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "live"
    assert body["id"]
    got = api_client.get(f"/api/v1/sessions/{body['id']}", headers=AUTH)
    assert got.status_code == 200
    assert got.json()["state"] == "live"


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
            flags["play_backend"] = kwargs.get("play_backend")

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
    assert flags["play_backend"] == "hil"
    body = started.json()
    assert body.get("session_source") == "fixture"
    assert body.get("play_attach", {}).get("backend") == "hil"
    assert body.get("play_attach", {}).get("ready") is True


def test_session_start_live_play_attaches_krpc(
    api_client: TestClient, game_slug: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registered install + play_enabled starts actions with explicit krpc/scs backend."""
    import titan_api.routers.sessions as sessions_routes
    from titan_core.play_attach import PlayAttach

    flags: dict[str, object] = {}

    class _Ctl:
        def start_orchestrator(self, session_id: UUID, **kwargs: object) -> None:
            flags["orch"] = True
            flags["orch_play"] = kwargs.get("play_enabled")

        def start_actions(self, session_id: UUID, **kwargs: object) -> None:
            flags["actions"] = True
            flags["play_backend"] = kwargs.get("play_backend")

        def stop_orchestrator(self, session_id: UUID) -> None:
            return

        def stop_actions(self, session_id: UUID) -> None:
            return

    api_client.app.state.session_controller = _Ctl()

    async def noop(*_a: object, **_k: object) -> None:
        return None

    expected_backend = "krpc" if game_slug == "ksp" else "scs" if game_slug in {"ets2", "ats"} else "hil"

    async def ready_attach(**_kwargs: object) -> PlayAttach:
        return PlayAttach(
            source="live",
            backend=expected_backend,  # type: ignore[arg-type]
            ready=True,
            message="ready",
            detail={},
        )

    monkeypatch.setattr(sessions_routes, "start_demo_replay", noop)
    monkeypatch.setattr(sessions_routes, "_seed_director_demo_line", noop)
    monkeypatch.setattr(sessions_routes, "start_live_telemetry", noop)
    monkeypatch.setattr(sessions_routes, "wait_probe_attach", ready_attach)

    exe = tmp_path / ("KSP_x64.exe" if game_slug == "ksp" else "eurotrucks2.exe")
    exe.write_bytes(b"MZ")
    registered = api_client.post(
        "/api/v1/game-profiles",
        headers=AUTH,
        json={"game_slug": game_slug, "executable_path": str(exe)},
    )
    assert registered.status_code == 201, registered.text
    profile_id = registered.json()["id"]

    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "game_profile_id": profile_id,
            "title": "live-play",
            "settings": {
                "agents_enabled": True,
                "play_enabled": True,
                "demo_telemetry": False,
                "session_source": "live",
            },
        },
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202, started.text
    assert flags.get("actions") and flags.get("orch")
    assert flags.get("orch_play") is True
    assert flags.get("play_backend") == expected_backend
    body = started.json()
    assert body.get("session_source") == "live"
    assert body.get("play_actions") is True
    assert body.get("play_attach", {}).get("backend") == expected_backend


def test_session_start_degrades_when_krpc_missing(
    api_client: TestClient, game_slug: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live play without kRPC still yields a live observe session (not a hard failure)."""
    if game_slug != "ksp":
        pytest.skip("kRPC degrade path is KSP-specific")
    import titan_api.routers.sessions as sessions_routes
    from titan_core.play_attach import PlayAttach

    flags: dict[str, object] = {"actions": 0}

    class _Ctl:
        def start_orchestrator(self, session_id: UUID, **kwargs: object) -> None:
            flags["orch_play"] = kwargs.get("play_enabled")

        def start_actions(self, session_id: UUID, **kwargs: object) -> None:
            flags["actions"] = int(flags["actions"]) + 1

        def stop_orchestrator(self, session_id: UUID) -> None:
            return

        def stop_actions(self, session_id: UUID) -> None:
            return

    api_client.app.state.session_controller = _Ctl()

    async def noop(*_a: object, **_k: object) -> None:
        return None

    async def not_ready(**_kwargs: object) -> PlayAttach:
        return PlayAttach(
            source="live",
            backend="krpc",
            ready=False,
            message="kRPC is not running. Install the kRPC mod under KSP/GameData.",
            detail={"degraded_to_observe": True, "krpc_mod_hint": True},
        )

    monkeypatch.setattr(sessions_routes, "start_demo_replay", noop)
    monkeypatch.setattr(sessions_routes, "_seed_director_demo_line", noop)
    monkeypatch.setattr(sessions_routes, "start_live_telemetry", noop)
    monkeypatch.setattr(sessions_routes, "wait_probe_attach", not_ready)

    exe = tmp_path / "KSP_x64.exe"
    exe.write_bytes(b"MZ")

    class _Proc:
        pid = 424242

    def _fake_popen(argv: list[str], *_args: object, **_kwargs: object) -> _Proc:
        flags["argv"] = list(argv)
        return _Proc()

    monkeypatch.setattr(sessions_routes.subprocess, "Popen", _fake_popen)
    registered = api_client.post(
        "/api/v1/game-profiles",
        headers=AUTH,
        json={"game_slug": "ksp", "executable_path": str(exe)},
    )
    assert registered.status_code == 201, registered.text
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": "ksp",
            "game_profile_id": registered.json()["id"],
            "title": "observe-fallback",
            "settings": {
                "agents_enabled": True,
                "play_enabled": True,
                "demo_telemetry": False,
                "session_source": "live",
            },
        },
    )
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": True})
    assert started.status_code == 202, started.text
    body = started.json()
    assert body["state"] == "live"
    assert body.get("play_actions") is False
    assert body.get("play_attach", {}).get("ready") is False
    assert "kRPC" in body.get("play_attach", {}).get("message", "")
    assert flags.get("orch_play") is False
    assert flags.get("actions") == 0
    assert body.get("game_pid") == 424242
    assert "launch_error" not in body
    argv = flags["argv"]
    assert isinstance(argv, list)
    assert str(argv[0]).endswith("KSP_x64.exe")
    assert argv[1:] == ["-screen-fullscreen", "0", "-popupwindow"]


def test_create_autonomous_with_play_coerces_to_observe(api_client: TestClient, game_slug: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "auto-play",
            "mode": "autonomous",
            "settings": {"play_enabled": True, "agents_enabled": False},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["mode"] == "observe"


def test_create_autonomous_without_play_rejected(api_client: TestClient, game_slug: str) -> None:
    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "auto-no-play",
            "mode": "autonomous",
            "settings": {"agents_enabled": False},
        },
    )
    assert created.status_code == 501


def test_session_play_toggle(api_client: TestClient, game_slug: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import titan_api.routers.sessions as sessions_routes

    flags: dict[str, object] = {"actions": 0, "orch_restart": 0, "stop_actions": 0}

    class _Ctl:
        def start_orchestrator(self, session_id: UUID, **kwargs: object) -> None:
            flags["orch"] = True

        def restart_orchestrator(self, session_id: UUID, **kwargs: object) -> None:
            flags["orch_restart"] = int(flags["orch_restart"]) + 1
            flags["restart_play"] = kwargs.get("play_enabled")

        def start_actions(self, session_id: UUID, **kwargs: object) -> None:
            flags["actions"] = int(flags["actions"]) + 1
            flags["play_backend"] = kwargs.get("play_backend")

        def stop_actions(self, session_id: UUID) -> None:
            flags["stop_actions"] = int(flags["stop_actions"]) + 1

        def stop_orchestrator(self, session_id: UUID) -> None:
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
            "title": "toggle-play",
            "settings": {"agents_enabled": True, "play_enabled": False, "demo_telemetry": True},
        },
    )
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202

    enabled = api_client.post(f"/api/v1/sessions/{sid}/play", headers=AUTH, json={"enabled": True})
    assert enabled.status_code == 202, enabled.text
    assert enabled.json().get("play_enabled") is True
    assert enabled.json().get("play_attach", {}).get("backend") == "hil"
    assert flags["orch_restart"] == 1 and flags["restart_play"] is True
    assert flags["actions"] >= 1

    disabled = api_client.post(f"/api/v1/sessions/{sid}/play", headers=AUTH, json={"enabled": False})
    assert disabled.status_code == 202
    assert disabled.json().get("play_enabled") is False
    assert flags["stop_actions"] >= 1


def test_session_start_exposes_failed_contracts_for_the_same_game(
    api_client: TestClient, game_slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A miss saved in the memory store is on the next session's board before the crew starts."""
    import asyncio

    import titan_api.memory_ops as memory_ops
    import titan_api.routers.sessions as sessions_routes
    from titan_memory.learnings import FailedContract, save_failed_contracts
    from titan_models.embedder import FakeEmbedder

    key = "altituderecord|reach 5000 m"
    title = "Reach 5,000 m"
    reason = "out of fuel at 2200 m"
    previous = "00000000-0000-4000-8000-00000000c0de"

    class _Store:
        def __init__(self) -> None:
            self.docs: dict[str, tuple[str, dict[str, object]]] = {}

        async def upsert(
            self,
            _collection: str,
            *,
            ids: list[str],
            documents: list[str],
            metadatas: list[dict[str, object]],
            embeddings: list[list[float]] | None = None,
        ) -> None:
            del embeddings
            for mem_id, document, metadata in zip(ids, documents, metadatas, strict=True):
                self.docs[mem_id] = (document, dict(metadata))

        async def query(self, _collection: str, **_kwargs: object) -> dict[str, object]:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]]}

        async def get(self, _collection: str, **_kwargs: object) -> dict[str, object]:
            ids = list(self.docs)
            return {
                "ids": ids,
                "documents": [self.docs[mem_id][0] for mem_id in ids],
                "metadatas": [self.docs[mem_id][1] for mem_id in ids],
            }

    store = _Store()
    asyncio.run(
        save_failed_contracts(
            store,
            FakeEmbedder(),
            [
                FailedContract(
                    contract_id=key,
                    title=title,
                    reason=reason,
                    session_id=previous,
                    game_slug=game_slug,
                ),
                FailedContract(
                    contract_id="survey|mun",
                    title="Survey the Mun",
                    reason="out of fuel",
                    session_id=previous,
                    game_slug="not-this-game",
                ),
            ],
        )
    )
    monkeypatch.setattr(memory_ops, "memory_store", lambda: store)

    class _Ctl:
        def start_orchestrator(self, session_id: UUID, **kwargs: object) -> None:
            del session_id, kwargs

        def start_actions(self, session_id: UUID, **kwargs: object) -> None:
            del session_id, kwargs

        def stop_orchestrator(self, session_id: UUID) -> None:
            del session_id

        def stop_actions(self, session_id: UUID) -> None:
            del session_id

    api_client.app.state.session_controller = _Ctl()

    async def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(sessions_routes, "start_demo_replay", noop)
    monkeypatch.setattr(sessions_routes, "start_live_telemetry", noop)

    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={
            "game_slug": game_slug,
            "title": "remember the miss",
            "settings": {"agents_enabled": True, "demo_telemetry": True},
        },
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    started = api_client.post(f"/api/v1/sessions/{sid}/start", headers=AUTH, json={"launch_game": False})
    assert started.status_code == 202, started.text

    board = api_client.get(f"/api/v1/sessions/{sid}/blackboard", headers=AUTH, params={"sections": "notes"})
    assert board.status_code == 200, board.text
    notes = {entry["key"]: entry["value"] for entry in board.json()["entries"] if entry["section"] == "notes"}
    missed = notes["prior.fail.00"]
    assert missed["ok"] is False
    assert missed["contract_key"] == key
    assert missed["contract_title"] == title
    assert missed["failure_reason"] == reason
    assert missed["session_id"] == previous
    assert f"contract key `{key}`" in missed["text"]
    assert "do not accept contract key" in missed["text"].lower()
    assert all(entry.get("contract_key") != "survey|mun" for entry in notes.values())
    assert notes["prior.seed"]["failed_contracts"] == 1


def test_play_readiness_endpoint(api_client: TestClient) -> None:
    fixture = api_client.get(
        "/api/v1/play/readiness", headers=AUTH, params={"game_slug": "ksp", "source": "fixture"}
    )
    assert fixture.status_code == 200
    assert fixture.json()["play_attach"]["backend"] == "hil"
    assert fixture.json()["play_attach"]["ready"] is True
    live = api_client.get(
        "/api/v1/play/readiness", headers=AUTH, params={"game_slug": "ksp", "source": "live"}
    )
    assert live.status_code == 200
    assert live.json()["play_attach"]["backend"] == "krpc"
