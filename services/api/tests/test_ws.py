from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from titan_api import ws
from titan_api.main import create_app
from titan_api.safety import SafetyController
from titan_core.clock import utc_now
from titan_core.config import TitanConfig
from titan_core.protocol.system import SupervisorStatus
from titan_core.protocol.ws import SystemMetrics
from titan_core.streams import SYS_METRICS

TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def no_supervisor() -> SupervisorStatus | None:
    return None


def metrics(cpu: float) -> SystemMetrics:
    return SystemMetrics(
        ts=utc_now(),
        game_fps=None,
        game_frametime_p99_ms=None,
        cpu_pct=cpu,
        ram_used_mb=1000,
        ram_total_mb=16000,
        gpu=[],
        tokens_per_min=0,
        llm_queue_depth=0,
        goals_active=0,
        tasks_open=0,
        resource_guard_level="L0",
    )


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


@pytest.fixture
def sync_redis(server: fakeredis.FakeServer) -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture
def client(server: fakeredis.FakeServer) -> Iterator[TestClient]:
    redis = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    app = create_app(
        TitanConfig(),
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=redis,
        start_persister=False,
        enable_database=False,
    )
    with TestClient(app) as test_client:
        yield test_client


def authed(client: TestClient) -> Any:
    session = client.websocket_connect("/api/v1/ws")
    conn = session.__enter__()
    conn.send_json({"op": "auth", "token": TOKEN, "client": "test/1.0"})
    assert conn.receive_json() == {"op": "ack", "req_id": "auth", "ok": True, "error": None}
    return session, conn


def test_wrong_token_closes_4401(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/ws") as conn:
        conn.send_json({"op": "auth", "token": "nope", "client": "test/1.0"})
        with pytest.raises(WebSocketDisconnect) as closed:
            conn.receive_json()
    assert closed.value.code == 4401


def test_first_frame_must_be_auth(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/ws") as conn:
        conn.send_json({"op": "ping", "req_id": "r1"})
        with pytest.raises(WebSocketDisconnect) as closed:
            conn.receive_json()
    assert closed.value.code == 4401


def test_auth_timeout_closes_4401(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "AUTH_TIMEOUT_S", 0.2)
    with client.websocket_connect("/api/v1/ws") as conn, pytest.raises(WebSocketDisconnect) as closed:
        conn.receive_json()
    assert closed.value.code == 4401


def test_foreign_origin_is_rejected(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect("/api/v1/ws", headers={"Origin": "https://evil.example"}),
    ):
        pass
    assert closed.value.code == 1008


def test_ping_and_bad_frames(client: TestClient) -> None:
    session, conn = authed(client)
    conn.send_json({"op": "ping", "req_id": "r1"})
    assert conn.receive_json() == {"op": "pong", "req_id": "r1"}
    conn.send_text("not json")
    bad = conn.receive_json()
    assert bad["ok"] is False
    assert bad["error"]["code"] == "VALIDATION_FAILED"
    conn.send_json({"op": "dance", "req_id": "r2"})
    assert conn.receive_json()["req_id"] == "r2"
    session.__exit__(None, None, None)


def test_channels(client: TestClient) -> None:
    session, conn = authed(client)
    conn.send_json({"op": "subscribe", "req_id": "s1", "channel": "session.0193abcd.chat"})
    assert conn.receive_json()["error"] == {"code": "NOT_FOUND", "detail": "unknown session"}
    conn.send_json({"op": "subscribe", "req_id": "s2", "channel": "nonsense"})
    assert conn.receive_json()["error"]["code"] == "VALIDATION_FAILED"
    conn.send_json({"op": "subscribe", "req_id": "s3", "channel": "jobs"})
    assert conn.receive_json()["ok"] is True
    conn.send_json({"op": "unsubscribe", "req_id": "s4", "channel": "jobs"})
    assert conn.receive_json() == {"op": "ack", "req_id": "s4", "ok": True, "error": None}
    session.__exit__(None, None, None)


def test_system_metrics_sends_latest_then_live(client: TestClient, sync_redis: fakeredis.FakeRedis) -> None:
    sync_redis.xadd(SYS_METRICS, {"data": metrics(1.0).model_dump_json()})
    latest_id = sync_redis.xadd(SYS_METRICS, {"data": metrics(2.0).model_dump_json()})
    with client.websocket_connect("/api/v1/ws") as conn:
        conn.send_json({"op": "auth", "token": TOKEN, "client": "test/1.0"})
        assert conn.receive_json() == {"op": "ack", "req_id": "auth", "ok": True, "error": None}
        conn.send_json({"op": "subscribe", "req_id": "m1", "channel": "system.metrics"})
        assert conn.receive_json()["ok"] is True
        first = conn.receive_json()
        assert first["op"] == "msg"
        assert first["channel"] == "system.metrics"
        assert first["type"] == "system.metrics"
        assert first["seq"] == latest_id
        assert first["data"]["cpu_pct"] == 2.0
        live_id = sync_redis.xadd(SYS_METRICS, {"data": metrics(3.0).model_dump_json()})
        live = conn.receive_json()
        assert live["seq"] == live_id
        assert live["data"]["cpu_pct"] == 3.0
        assert live["data"]["game_fps"] is None


def test_system_safety_pushes_changes(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/ws") as conn:
        conn.send_json({"op": "auth", "token": TOKEN, "client": "test/1.0"})
        assert conn.receive_json() == {"op": "ack", "req_id": "auth", "ok": True, "error": None}
        conn.send_json({"op": "subscribe", "req_id": "k1", "channel": "system.safety"})
        assert conn.receive_json()["ok"] is True
        initial = conn.receive_json()
        assert initial["type"] == "safety.state"
        assert initial["data"]["killed"] is False
        client.post("/api/v1/safety/kill", json={"source": "hotkey"}, headers=AUTH)
        killed = conn.receive_json()
        assert killed["data"]["killed"] is True
        assert killed["data"]["last_kill_source"] == "hotkey"


def test_metrics_rest_endpoint(client: TestClient, sync_redis: fakeredis.FakeRedis) -> None:
    missing = client.get("/api/v1/system/metrics", headers=AUTH)
    assert missing.status_code == 404
    sync_redis.xadd(SYS_METRICS, {"data": metrics(7.5).model_dump_json()})
    body = client.get("/api/v1/system/metrics", headers=AUTH).json()
    assert body["cpu_pct"] == 7.5
    assert body["gpu"] == []


def test_metrics_rest_endpoint_without_redis() -> None:
    import redis.asyncio as aioredis

    redis = aioredis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    app = create_app(
        TitanConfig(),
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=redis,
        start_persister=False,
        enable_database=False,
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/system/metrics", headers=AUTH)
    assert response.status_code == 503
    assert response.json()["dependency"] == "redis"


# ---------------------------------------------------------------- backpressure (Section 5.3)
def test_send_buffer_metrics_are_latest_wins() -> None:
    buffer = ws.SendBuffer(limit=3)
    assert buffer.put("m1", coalesce="system.metrics")
    assert buffer.put("chat1")
    assert buffer.put("m2", coalesce="system.metrics")
    assert len(buffer) == 2


async def test_send_buffer_drops_telemetry_first_then_overflows() -> None:
    buffer = ws.SendBuffer(limit=2)
    assert buffer.put("m1", coalesce="system.metrics")
    assert buffer.put("chat1")
    assert buffer.put("telemetry", coalesce="session.x.telemetry")  # full: dropped, not an overflow
    assert buffer.put("chat2")  # full: evicts m1
    assert not buffer.put("chat3")  # full of frames that must not be dropped
    assert [await buffer.get(), await buffer.get()] == ["chat1", "chat2"]


class StuckSocket:
    """A client that never reads: every send blocks."""

    def __init__(self) -> None:
        self.closed_with: int | None = None

    async def send_text(self, text: str) -> None:
        await asyncio.Event().wait()

    async def receive_text(self) -> str:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


async def test_overflow_closes_4408() -> None:
    socket = StuckSocket()
    connection = ws.Connection(socket, fakeredis.FakeAsyncRedis(), SafetyController(None))  # type: ignore[arg-type]
    runner = asyncio.create_task(connection.run())
    await asyncio.sleep(0)
    for index in range(ws.SEND_BUFFER_FRAMES + 1):
        connection.ack(f"r{index}")
    await asyncio.wait_for(runner, 2)
    assert socket.closed_with == 4408


def test_frames_match_the_protocol(client: TestClient) -> None:
    from titan_core.protocol.ws import ServerFrame

    session, conn = authed(client)
    conn.send_json({"op": "subscribe", "req_id": "k1", "channel": "system.safety"})
    for _ in range(2):
        ServerFrame.model_validate_json(json.dumps(conn.receive_json()))
    session.__exit__(None, None, None)
