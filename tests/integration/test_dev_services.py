"""Backing services from docker-compose.yml / CI service containers are reachable on the configured ports."""

from __future__ import annotations

import json
import os
import socket
import urllib.request
from urllib.parse import urlparse

import pytest

from titan_core.config import TitanConfig, load_config

REQUIRED = os.environ.get("TITAN_REQUIRE_SERVICES") == "1"


@pytest.fixture(scope="module")
def config() -> TitanConfig:
    return load_config(user_config=False)


def _unavailable(what: str, exc: Exception) -> None:
    if REQUIRED:
        pytest.fail(f"{what} unavailable but TITAN_REQUIRE_SERVICES=1: {exc}")
    pytest.skip(f"{what} unavailable: {exc}")


def test_redis_ping(config: TitanConfig) -> None:
    url = urlparse(config.redis.url)
    try:
        with socket.create_connection((url.hostname or "127.0.0.1", url.port or 6379), timeout=3) as sock:
            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            reply = sock.recv(64)
    except OSError as exc:
        _unavailable("redis", exc)
    assert reply == b"+PONG\r\n"


def test_chroma_heartbeat(config: TitanConfig) -> None:
    url = f"http://127.0.0.1:{config.chroma.port}/api/v2/heartbeat"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = json.load(response)
    except OSError as exc:
        _unavailable("chroma", exc)
    assert isinstance(body, dict)
    assert body
