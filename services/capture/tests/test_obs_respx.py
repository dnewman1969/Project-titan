from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from websockets.asyncio.server import ServerConnection, serve

from titan_capture.obs import OP_IDENTIFIED, OP_REQUEST, OP_REQUEST_RESPONSE, ObsClient


async def _mock_obs_handler(connection: ServerConnection) -> None:
    hello = {
        "op": 0,
        "d": {"obsWebSocketVersion": "5.0.1", "rpcVersion": 1},
    }
    await connection.send(json.dumps(hello))
    raw = await connection.recv()
    identify = json.loads(str(raw))
    assert identify.get("op") == 1
    await connection.send(json.dumps({"op": OP_IDENTIFIED, "d": {"negotiatedRpcVersion": 1}}))
    async for message in connection:
        payload = json.loads(str(message))
        if payload.get("op") != OP_REQUEST:
            continue
        data = payload.get("d")
        if not isinstance(data, dict):
            continue
        request_type = data.get("requestType")
        request_id = data.get("requestId")
        if request_type == "GetVersion":
            response_data = {"obsVersion": "30.0.0", "obsWebSocketVersion": "5.0.1", "rpcVersion": 1}
        elif request_type == "GetRecordStatus":
            response_data = {"outputActive": True, "outputPaused": False, "outputTimecode": 12_500}
        elif request_type in {"StartRecord", "StopRecord"}:
            response_data = {}
        else:
            response_data = {}
        reply = {
            "op": OP_REQUEST_RESPONSE,
            "d": {
                "requestType": request_type,
                "requestId": request_id,
                "requestStatus": {"code": 100, "result": True},
                "responseData": response_data,
            },
        }
        await connection.send(json.dumps(reply))


@pytest.fixture
async def obs_ws_server() -> AsyncIterator[str]:
    async with serve(_mock_obs_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_obs_client_handshake_and_record_status(obs_ws_server: str) -> None:
    host, port_s = obs_ws_server.removeprefix("ws://").split(":")
    client = ObsClient(host, int(port_s))
    await client.connect()
    try:
        version = await client.get_version()
        assert version["obsVersion"] == "30.0.0"
        status = await client.get_record_status()
        assert status.active is True
        assert status.duration_ms == 12_500
        await client.start_recording()
        plan = await client.provision_titan_profile()
        assert plan["status"] == "planned"
        assert plan["obs_version"] == "30.0.0"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_obs_probe_http_with_respx() -> None:
    route = respx.get("http://127.0.0.1:4455/").mock(
        return_value=httpx.Response(426, text="Upgrade Required")
    )
    client = ObsClient()
    assert await client.probe_http() is True
    assert route.called


@pytest.mark.asyncio
async def test_obs_provision_profile_requires_connection() -> None:
    with pytest.raises(RuntimeError, match="OBS not running"):
        await ObsClient().provision_titan_profile()
