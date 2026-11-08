from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient

from titan_api.main import create_app
from titan_api.safety import SafetyController
from titan_core.config import TitanConfig
from titan_core.protocol.system import SupervisorStatus
from titan_core.protocol.ws import SafetyState
from titan_core.streams import SAFETY_STATE

TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def no_supervisor() -> SupervisorStatus | None:
    return None


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


def make_client(server: fakeredis.FakeServer) -> TestClient:
    redis = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    app = create_app(
        TitanConfig(),
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=redis,
        start_persister=False,
    )
    return TestClient(app)


@pytest.fixture
def client(server: fakeredis.FakeServer) -> Iterator[TestClient]:
    with make_client(server) as test_client:
        yield test_client


def test_initial_state_is_disarmed(client: TestClient) -> None:
    body = client.get("/api/v1/safety/state", headers=AUTH).json()
    assert body == {
        "killed": False,
        "armed": False,
        "control_owner": "none",
        "last_kill_at": None,
        "last_kill_source": None,
        "policy_version": 1,
    }


def test_safety_routes_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/safety/state").status_code == 401
    assert client.post("/api/v1/safety/kill", json={"source": "hotkey"}).status_code == 401


def test_kill_then_resume(client: TestClient, server: fakeredis.FakeServer) -> None:
    killed = client.post("/api/v1/safety/kill", json={"source": "hotkey"}, headers=AUTH)
    assert killed.status_code == 200
    body = killed.json()
    assert body["killed"] is True
    assert body["armed"] is False
    assert body["last_kill_source"] == "hotkey"
    assert body["last_kill_at"] is not None
    assert client.get("/api/v1/safety/state", headers=AUTH).json()["killed"] is True

    stored = fakeredis.FakeRedis(server=server, decode_responses=True).hgetall(SAFETY_STATE)
    assert json.loads(stored["killed"]) is True
    assert json.loads(stored["last_kill_source"]) == "hotkey"

    resumed = client.post("/api/v1/safety/resume", json={"confirm": "RESUME"}, headers=AUTH)
    assert resumed.status_code == 200
    assert resumed.json()["killed"] is False
    assert resumed.json()["last_kill_source"] == "hotkey"


def test_resume_needs_the_confirmation_word(client: TestClient) -> None:
    response = client.post("/api/v1/safety/resume", json={"confirm": "yes"}, headers=AUTH)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_arm_is_locked_in_phase_1(client: TestClient) -> None:
    response = client.post(
        "/api/v1/safety/arm",
        json={"session_id": "0193f0c0-0000-7000-8000-000000000000", "confirm": "ARM"},
        headers=AUTH,
    )
    assert response.status_code == 423
    assert response.json()["code"] == "SAFETY_LOCKED"


def test_kill_answers_in_under_50_ms(client: TestClient) -> None:
    durations = []
    for _ in range(20):
        start = time.perf_counter()
        response = client.post("/api/v1/safety/kill", json={"source": "hotkey"}, headers=AUTH)
        durations.append(time.perf_counter() - start)
        assert response.status_code == 200
    assert statistics.median(durations) < 0.05


def test_kill_survives_an_api_restart(server: fakeredis.FakeServer) -> None:
    with make_client(server) as first:
        first.post("/api/v1/safety/kill", json={"source": "ui"}, headers=AUTH)
    with make_client(server) as second:
        body = second.get("/api/v1/safety/state", headers=AUTH).json()
    assert body["killed"] is True
    assert body["armed"] is False
    assert body["last_kill_source"] == "ui"


async def test_kill_works_without_redis() -> None:
    import redis.asyncio as aioredis

    unreachable = aioredis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    controller = SafetyController(unreachable)
    await controller.load()
    start = time.perf_counter()
    state = controller.kill("hotkey")
    assert time.perf_counter() - start < 0.05
    assert state.killed is True
    await controller.drain()
    await unreachable.aclose()


async def test_listeners_see_every_change() -> None:
    controller = SafetyController(None)
    seen: list[SafetyState] = []
    unsubscribe = controller.subscribe(seen.append)
    controller.kill("hotkey")
    controller.resume()
    unsubscribe()
    controller.kill("ui")
    assert [s.killed for s in seen] == [True, False]


async def test_kill_publishes_on_the_kill_channel() -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("titan:safety:kill")
    await pubsub.get_message(timeout=1)
    controller = SafetyController(redis)
    controller.kill("hotkey")
    await controller.drain()
    message = await pubsub.get_message(timeout=1)
    assert message is not None
    assert json.loads(message["data"])["last_kill_source"] == "hotkey"
    await pubsub.aclose()
    await redis.aclose()
