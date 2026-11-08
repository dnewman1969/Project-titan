"""Backing services from docker-compose.yml / CI service containers are reachable on the configured ports."""

from __future__ import annotations

import json
import os
import socket
import urllib.request
from urllib.parse import urlparse

import pytest
import redis.exceptions

from titan_core.config import TitanConfig, load_config
from titan_core.health import check_redis
from titan_core.ids import new_id
from titan_core.streams import redis_client

REQUIRED = os.environ.get("TITAN_REQUIRE_SERVICES") == "1"


@pytest.fixture(scope="module")
def config() -> TitanConfig:
    return load_config(user_config=False)


def _unavailable(what: str, exc: Exception) -> None:
    if REQUIRED:
        pytest.fail(f"{what} unavailable but TITAN_REQUIRE_SERVICES=1: {exc}")
    pytest.skip(f"{what} unavailable: {exc}")


def _resp(*parts: str) -> bytes:
    out = f"*{len(parts)}\r\n"
    for part in parts:
        out += f"${len(part.encode())}\r\n{part}\r\n"
    return out.encode()


def test_redis_requires_a_password_and_accepts_ours(config: TitanConfig) -> None:
    """M1.T2: Titan's Redis runs with requirepass; TITAN__REDIS__PASSWORD holds the dev/CI value."""
    url = urlparse(config.redis.url)
    password = config.redis.password.get_secret_value() if config.redis.password else None
    try:
        with socket.create_connection((url.hostname or "127.0.0.1", url.port or 6379), timeout=3) as sock:
            sock.sendall(_resp("PING"))
            anonymous = sock.recv(256)
            if password:
                sock.sendall(_resp("AUTH", password))
                auth = sock.recv(64)
                sock.sendall(_resp("PING"))
                reply = sock.recv(64)
    except OSError as exc:
        _unavailable("redis", exc)
    if not password:
        _unavailable("redis password", RuntimeError("TITAN__REDIS__PASSWORD is not set"))
    assert anonymous.startswith(b"-NOAUTH"), anonymous
    assert auth == b"+OK\r\n"
    assert reply == b"+PONG\r\n"


async def test_redis_replies_have_the_shapes_we_parse(config: TitanConfig) -> None:
    """RESP2 replies (`XREAD` as a list, `HGETALL` as a dict) and a requirepass server reports `up`."""
    client = redis_client(config.redis)
    stream = f"titan:test:{new_id()}"
    try:
        entry_id = await client.xadd(stream, {"data": "{}"})
        reply = await client.xread({stream: "0-0"}, count=1)
        await client.hset(stream + ":h", mapping={"a": "1"})
        fields = await client.hgetall(stream + ":h")
    except (redis.exceptions.RedisError, OSError) as exc:
        _unavailable("redis", exc)
    finally:
        await client.delete(stream, stream + ":h")
        await client.aclose()
    assert reply == [[stream, [(entry_id, {"data": "{}"})]]]
    assert fields == {"a": "1"}
    if config.redis.password is not None:
        assert (await check_redis(config.redis)).state == "up"


def test_chroma_heartbeat(config: TitanConfig) -> None:
    url = f"http://127.0.0.1:{config.chroma.port}/api/v2/heartbeat"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = json.load(response)
    except OSError as exc:
        _unavailable("chroma", exc)
    assert isinstance(body, dict)
    assert body
