"""Dependency checks (Sections 2.3 and 5.2): never raise, report up / degraded / down."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import redis.exceptions
from pydantic import SecretStr

from titan_core import health
from titan_core.config import ChromaConfig, PostgresConfig, RedisConfig
from titan_core.http import EgressBlocked, local_client
from titan_core.protocol.system import DependencyState

Routes = dict[str, tuple[int, object]]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _serve(routes: Routes) -> tuple[asyncio.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await reader.readuntil(b"\r\n\r\n")
        path = request.split(b" ", 2)[1].decode()
        status, body = routes.get(path, (404, {"detail": "nope"}))
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Length: {len(payload)}\r\n"
            "Content-Type: application/json\r\nConnection: close\r\n\r\n".encode()
            + payload
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, int(server.sockets[0].getsockname()[1])


@pytest.fixture
async def http_server() -> AsyncIterator[Callable[[Routes], Any]]:
    servers: list[asyncio.Server] = []

    async def start(routes: Routes) -> int:
        server, port = await _serve(routes)
        servers.append(server)
        return port

    yield start
    for server in servers:
        server.close()
        await server.wait_closed()


async def test_local_client_refuses_other_hosts() -> None:
    async with local_client() as client:
        with pytest.raises(EgressBlocked):
            await client.get("http://example.com/")


async def test_local_client_sends_the_bearer_token() -> None:
    client = local_client(token="tok")
    assert client.headers["authorization"] == "Bearer tok"
    await client.aclose()


async def test_http_states(http_server: Callable[[Routes], Any]) -> None:
    port = await http_server(
        {"/ok": (200, {"version": "0.9"}), "/bad": (500, {}), "/text": (200, "not json")}
    )
    base = f"http://127.0.0.1:{port}"
    assert await health.check_http(f"{base}/ok", version_key="version") == DependencyState(
        state="up", version="0.9"
    )
    assert await health.check_http(f"{base}/text", version_key="version") == DependencyState(state="up")
    assert await health.check_http(f"{base}/bad") == DependencyState(state="degraded", detail="HTTP 500")
    down = await health.check_http(f"http://127.0.0.1:{free_port()}/")
    # Windows retries a refused SYN for about 2 s, so the 1 s timeout usually fires first.
    assert down.state == "down" and down.detail in {"ConnectError", "ConnectTimeout"}


async def test_ollama_and_chroma(http_server: Callable[[Routes], Any]) -> None:
    port = await http_server(
        {
            "/api/version": (200, {"version": "0.12.0"}),
            "/api/v2/heartbeat": (200, {"nanosecond heartbeat": 1}),
        }
    )
    assert (await health.check_ollama(f"http://127.0.0.1:{port}")).version == "0.12.0"
    chroma = await health.check_chroma(ChromaConfig(port=port))
    assert chroma == DependencyState(state="up")
    versioned = await http_server({"/api/v2/heartbeat": (200, {}), "/api/v2/version": (200, "1.5.9")})
    assert (await health.check_chroma(ChromaConfig(port=versioned))).state == "up"
    quoted = await http_server({"/api/v2/heartbeat": (200, {}), "/api/v2/version": (200, '"1.5.9"')})
    assert (await health.check_chroma(ChromaConfig(port=quoted))).version == "1.5.9"
    assert (await health.check_chroma(ChromaConfig(port=free_port()))).state == "down"


async def test_tcp_and_obs() -> None:
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    try:
        assert await health.check_tcp("127.0.0.1", port) == DependencyState(state="up")
    finally:
        server.close()
        await server.wait_closed()
    assert (await health.check_tcp("127.0.0.1", free_port())).state == "down"
    assert (await health.check_obs(timeout_s=0.5)).state in {"up", "down"}
    assert (await health.check_obs("127.0.0.1", 1, timeout_s=0.2)).state == "down"


async def test_timed_reports_overruns() -> None:
    async def slow() -> DependencyState:
        await asyncio.sleep(5)
        return DependencyState(state="up")

    async def fast() -> DependencyState:
        return DependencyState(state="up")

    late = await health.timed(slow, 0.05)
    assert late.state == "down" and late.detail is not None and late.detail.startswith("timeout after")
    assert (await health.timed(fast, 1)).state == "up"


async def test_postgres_unreachable() -> None:
    state = await health.check_postgres(
        PostgresConfig(port=free_port(), password=SecretStr("x")), timeout_s=0.5
    )
    assert state.state == "down"


class FakeRedis:
    """Stands in for `redis.asyncio.Redis`: the authenticated and the anonymous client."""

    def __init__(self, *, password: str | None, server_password: str | None, alive: bool = True) -> None:
        self.password = password
        self.server_password = server_password
        self.alive = alive

    def _check(self) -> None:
        if not self.alive:
            raise redis.exceptions.ConnectionError("refused")
        if self.server_password is not None and self.password != self.server_password:
            if self.password is None:
                raise redis.exceptions.AuthenticationError("NOAUTH")
            raise redis.exceptions.AuthenticationError("WRONGPASS")

    async def info(self, _section: str) -> dict[str, str]:
        self._check()
        return {"redis_version": "7.4.12"}

    async def ping(self) -> bool:
        self._check()
        return True

    async def aclose(self) -> None:
        return None


def fake_server(monkeypatch: pytest.MonkeyPatch, server_password: str | None, *, alive: bool = True) -> None:
    def from_url(_url: str, *, password: str | None = None, **_kw: object) -> FakeRedis:
        return FakeRedis(password=password, server_password=server_password, alive=alive)

    monkeypatch.setattr(health.aioredis.Redis, "from_url", from_url)


async def test_redis_with_requirepass_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_server(monkeypatch, "pw")
    state = await health.check_redis(RedisConfig(password=SecretStr("pw")))
    assert state == DependencyState(state="up", version="7.4.12")


async def test_redis_without_requirepass_is_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_server(monkeypatch, None)
    state = await health.check_redis(RedisConfig(password=SecretStr("pw")))
    assert state == DependencyState(state="degraded", version="7.4.12", detail="requirepass is not set")


async def test_redis_wrong_password_and_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_server(monkeypatch, "right")
    wrong = await health.check_redis(RedisConfig(password=SecretStr("wrong")))
    assert wrong.state == "down" and wrong.detail is not None and "titan/redis" in wrong.detail
    fake_server(monkeypatch, "right", alive=False)
    assert (await health.check_redis(RedisConfig(password=SecretStr("right")))).detail == "ConnectionError"
