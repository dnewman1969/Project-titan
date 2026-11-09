"""obs-websocket v5 client: auth string + Identify handshake (CI mock server)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

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


def test_timecode_and_camera_name_rules() -> None:
    from titan_core.obs_ws import camera_name_matches, timecode_to_ms

    assert timecode_to_ms(12_500) == 12_500
    assert timecode_to_ms("00:00:12.500") == 12_500
    assert timecode_to_ms("01:02:03:4") == (1 * 3600 + 2 * 60 + 3) * 1000 + 4
    assert timecode_to_ms("nope") is None
    assert camera_name_matches("OBSBOT Tiny 4K")
    assert camera_name_matches("usb-tiny-cam")
    assert not camera_name_matches("Integrated Camera")


def test_connection_refused_is_obs_not_running() -> None:
    from titan_core.obs_ws import obs_connection_failure

    state, detail = obs_connection_failure(ConnectionRefusedError(111, "refused"))
    assert state == "down"
    assert detail == "OBS not running"
    state, detail = obs_connection_failure(
        RuntimeError("OBS websocket authentication required; set TITAN__OBS__PASSWORD")
    )
    assert state == "degraded"
    assert "TITAN__OBS__PASSWORD" in detail


def test_make_obs_client_reads_keyring_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    monkeypatch.delenv("TITAN__OBS__PASSWORD", raising=False)

    def _resolve(configured: object, name: str) -> SecretStr | None:
        assert name == "obs"
        assert configured is None
        return SecretStr("from-keyring")

    monkeypatch.setattr("titan_core.secrets.resolve_secret", _resolve)
    client = make_obs_client()
    assert client.password == "from-keyring"


async def _mock_obs_webcam(connection: ServerConnection) -> None:
    await connection.send(json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.1", "rpcVersion": 1}}))
    raw = await connection.recv()
    identify = json.loads(str(raw))
    assert identify.get("op") == OP_IDENTIFY
    await connection.send(json.dumps({"op": OP_IDENTIFIED, "d": {"negotiatedRpcVersion": 1}}))
    created = False
    async for message in connection:
        payload = json.loads(str(message))
        if payload.get("op") != OP_REQUEST:
            continue
        data = payload.get("d")
        if not isinstance(data, dict):
            continue
        request_type = data.get("requestType")
        request_data = data.get("requestData") if isinstance(data.get("requestData"), dict) else {}
        response: dict[str, object] = {}
        if request_type == "GetInputList":
            inputs = [{"inputName": "Titan Webcam", "inputKind": "dshow_input"}] if created else []
            response = {"inputs": inputs}
        elif request_type == "GetSceneList":
            response = {"currentProgramSceneName": "Scene", "scenes": [{"sceneName": "Scene"}]}
        elif request_type == "CreateInput":
            assert request_data.get("inputName") == "Titan Webcam"
            assert request_data.get("inputKind") == "dshow_input"
            created = True
            response = {"sceneItemId": 1}
        elif request_type == "GetInputPropertiesListPropertyItems":
            response = {
                "propertyItems": [
                    {
                        "itemName": "Integrated Camera",
                        "itemValue": "Integrated Camera:usb",
                        "itemEnabled": True,
                    },
                    {
                        "itemName": "OBSBOT Tiny",
                        "itemValue": "OBSBOT Tiny:usb#vid_obsbot",
                        "itemEnabled": True,
                    },
                ]
            }
        elif request_type == "SetInputSettings":
            settings = request_data.get("inputSettings")
            assert isinstance(settings, dict)
            assert settings.get("video_device_id") == "OBSBOT Tiny:usb#vid_obsbot"
            response = {}
        elif request_type == "StartRecord":
            response = {}
        reply = {
            "op": OP_REQUEST_RESPONSE,
            "d": {
                "requestType": request_type,
                "requestId": data.get("requestId"),
                "requestStatus": {"code": 100, "result": True},
                "responseData": response,
            },
        }
        await connection.send(json.dumps(reply))


@pytest.fixture
async def obs_ws_webcam() -> AsyncIterator[tuple[str, int]]:
    async with serve(_mock_obs_webcam, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield "127.0.0.1", port


@pytest.mark.asyncio
async def test_select_obsbot_and_start_record(obs_ws_webcam: tuple[str, int], tmp_path: Path) -> None:
    host, port = obs_ws_webcam
    client = ObsClient(host, port, timeout_s=2.0)
    await client.connect()
    try:
        selected = await client.select_webcam_source()
        assert selected["selected"] is True
        assert selected["device_name"] == "OBSBOT Tiny"
        assert selected["device_id"] == "OBSBOT Tiny:usb#vid_obsbot"
        assert selected["input_name"] == "Titan Webcam"
        await client.start_recording(directory=str(tmp_path))
    finally:
        await client.close()


def test_make_obs_client_reads_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN__OBS__HOST", "10.0.0.9")
    monkeypatch.setenv("TITAN__OBS__PORT", "4456")
    monkeypatch.setenv("TITAN__OBS__PASSWORD", "from-env")
    client = make_obs_client()
    assert client.host == "10.0.0.9"
    assert client.port == 4456
    assert client.password == "from-env"
