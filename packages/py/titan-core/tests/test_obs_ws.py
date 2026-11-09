"""obs-websocket v5 client: auth string + Identify handshake (CI mock server)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from websockets.asyncio.server import ServerConnection, serve

from titan_core.obs_ws import (
    OP_IDENTIFIED,
    OP_IDENTIFY,
    OP_REQUEST,
    OP_REQUEST_RESPONSE,
    ObsClient,
    make_obs_client,
    obs_auth_string,
)


def test_obs_auth_string_is_stable() -> None:
    salt = "ZRDhizqZqWGgASrXBOwDK0REXUnxpXHgC4mDPgMSklU="
    challenge = "rj3ydfKRrhIlVWM22l48L9iujFi89L/+6iIp3WM7KSk="
    first = obs_auth_string("supersecret", salt, challenge)
    second = obs_auth_string("supersecret", salt, challenge)
    assert first == second
    assert len(first) > 20
    assert first != obs_auth_string("other", salt, challenge)


async def _mock_obs_no_auth(connection: ServerConnection) -> None:
    await connection.send(json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.1", "rpcVersion": 1}}))
    raw = await connection.recv()
    identify = json.loads(str(raw))
    assert identify.get("op") == OP_IDENTIFY
    assert "authentication" not in (identify.get("d") or {})
    await connection.send(json.dumps({"op": OP_IDENTIFIED, "d": {"negotiatedRpcVersion": 1}}))
    async for message in connection:
        payload = json.loads(str(message))
        if payload.get("op") != OP_REQUEST:
            continue
        data = payload.get("d")
        if not isinstance(data, dict):
            continue
        reply = {
            "op": OP_REQUEST_RESPONSE,
            "d": {
                "requestType": data.get("requestType"),
                "requestId": data.get("requestId"),
                "requestStatus": {"code": 100, "result": True},
                "responseData": {
                    "obsVersion": "30.0.0",
                    "outputActive": False,
                    "outputPaused": False,
                    "outputTimecode": 0,
                },
            },
        }
        await connection.send(json.dumps(reply))


async def _mock_obs_with_auth(connection: ServerConnection) -> None:
    salt = "test-salt"
    challenge = "test-challenge"
    await connection.send(
        json.dumps(
            {
                "op": 0,
                "d": {
                    "obsWebSocketVersion": "5.0.1",
                    "rpcVersion": 1,
                    "authentication": {"salt": salt, "challenge": challenge},
                },
            }
        )
    )
    raw = await connection.recv()
    identify = json.loads(str(raw))
    assert identify.get("op") == OP_IDENTIFY
    auth = (identify.get("d") or {}).get("authentication")
    assert auth == obs_auth_string("sekrit", salt, challenge)
    await connection.send(json.dumps({"op": OP_IDENTIFIED, "d": {"negotiatedRpcVersion": 1}}))
    async for _message in connection:
        pass


@pytest.fixture
async def obs_ws_no_auth() -> AsyncIterator[tuple[str, int]]:
    async with serve(_mock_obs_no_auth, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield "127.0.0.1", port


@pytest.fixture
async def obs_ws_auth() -> AsyncIterator[tuple[str, int]]:
    async with serve(_mock_obs_with_auth, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield "127.0.0.1", port


@pytest.mark.asyncio
async def test_connect_without_auth(obs_ws_no_auth: tuple[str, int]) -> None:
    host, port = obs_ws_no_auth
    client = ObsClient(host, port)
    await client.connect()
    try:
        version = await client.get_version()
        assert version["obsVersion"] == "30.0.0"
        await client.start_recording()
        await client.stop_recording()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_connect_with_auth(obs_ws_auth: tuple[str, int]) -> None:
    host, port = obs_ws_auth
    client = ObsClient(host, port, password="sekrit")
    await client.connect()
    await client.close()


@pytest.mark.asyncio
async def test_connect_requires_password_when_obs_auth_enabled(obs_ws_auth: tuple[str, int]) -> None:
    host, port = obs_ws_auth
    client = ObsClient(host, port, password="")
    with pytest.raises(RuntimeError, match="TITAN__OBS__PASSWORD"):
        await client.connect()


def test_make_obs_client_reads_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN__OBS__HOST", "10.0.0.9")
    monkeypatch.setenv("TITAN__OBS__PORT", "4456")
    monkeypatch.setenv("TITAN__OBS__PASSWORD", "from-env")
    client = make_obs_client()
    assert client.host == "10.0.0.9"
    assert client.port == 4456
    assert client.password == "from-env"
