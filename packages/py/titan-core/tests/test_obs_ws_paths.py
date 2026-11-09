"""Branch coverage for obs-websocket record control and webcam selection."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
from websockets.exceptions import WebSocketException

from titan_core.obs_ws import (
    OUTPUT_NOT_RUNNING,
    OUTPUT_RUNNING,
    ObsClient,
    ObsConnectionError,
    ObsRequestError,
    camera_name_matches,
    make_obs_client,
    obs_connection_failure,
    timecode_to_ms,
)

Reply = Callable[[dict[str, Any]], Any]


def _frame(
    request_id: str,
    data: dict[str, Any] | None = None,
    *,
    ok: bool = True,
    code: int | str = 100,
    comment: str | None = None,
    status: object | None = None,
) -> str:
    if status is None:
        built: dict[str, Any] = {"result": ok, "code": code}
        if comment is not None:
            built["comment"] = comment
        status = built
    body: dict[str, Any] = {"op": 7, "d": {"requestId": request_id, "requestStatus": status}}
    if data is not None:
        body["d"]["responseData"] = data
    return json.dumps(body)


class FakeSocket:
    """In-memory obs-websocket peer. Queued frames are returned before `reply`."""

    def __init__(
        self,
        incoming: list[object] | None = None,
        reply: Reply | None = None,
        *,
        send_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.incoming = list(incoming or [])
        self.reply = reply
        self.sent: list[str] = []
        self.send_error = send_error
        self.close_error = close_error

    async def send(self, data: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(data)

    async def recv(self) -> object:
        if self.incoming:
            item = self.incoming.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        if self.reply is None:
            msg = "no queued frame"
            raise RuntimeError(msg)
        payload = json.loads(self.sent[-1])
        item = self.reply(payload)
        if isinstance(item, list):
            self.incoming.extend(item[1:])
            item = item[0]
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error


def _install(monkeypatch: pytest.MonkeyPatch, sock: FakeSocket) -> ObsClient:
    async def _connect(_url: str, **kwargs: object) -> FakeSocket:
        assert kwargs.get("compression") is None
        return sock

    monkeypatch.setattr("titan_core.obs_ws.ws_connect", _connect)
    return ObsClient("127.0.0.1", 9, timeout_s=0.2)


def _hello() -> str:
    return json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.1", "rpcVersion": 1}})


def _identified() -> str:
    return json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}})


def _ready(reply: Reply) -> tuple[ObsClient, FakeSocket]:
    sock = FakeSocket(reply=reply)
    client = ObsClient(timeout_s=0.2)
    client._ws = sock  # type: ignore[assignment]
    return client, sock


def _script(table: dict[str, list[object]]) -> Reply:
    queues = {kind: list(items) for kind, items in table.items()}

    def reply(payload: dict[str, Any]) -> str:
        data = payload["d"]
        kind = str(data["requestType"])
        queue = queues[kind]
        item: object = queue.pop(0) if len(queue) > 1 else queue[0]
        request_id = str(data["requestId"])
        if isinstance(item, tuple) and item and item[0] == "fail":
            comment = item[2] if len(item) > 2 else None
            return _frame(
                request_id, ok=False, code=item[1], comment=comment if isinstance(comment, str) else None
            )
        if not isinstance(item, dict):
            msg = "script item must be a dict or fail tuple"
            raise AssertionError(msg)
        return _frame(request_id, item)

    return reply


def _status(
    *, active: bool, duration: object | None = None, timecode: object | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"outputActive": active, "outputPaused": active}
    if duration is not None:
        body["outputDuration"] = duration
    if timecode is not None:
        body["outputTimecode"] = timecode
    return body


def test_timecode_and_connection_failure_edges() -> None:
    assert timecode_to_ms(True) is None
    assert timecode_to_ms(1.5) == 1
    assert timecode_to_ms(object()) is None
    assert timecode_to_ms("   ") is None
    assert timecode_to_ms("aa:bb:cc") is None
    assert timecode_to_ms("1:2:3:x") is None
    assert timecode_to_ms("1:2") is None
    assert not camera_name_matches("")

    refused = OSError("plain")
    refused.errno = 61
    assert obs_connection_failure(refused) == ("down", "OBS not running")
    win = OSError("plain")
    win.errno = 10061
    assert obs_connection_failure(win)[0] == "down"
    other = OSError("plain")
    other.errno = 1
    assert obs_connection_failure(other) == ("degraded", "plain")
    assert obs_connection_failure(TimeoutError())[0] == "down"

    class Blank(Exception):
        def __str__(self) -> str:
            return "  "

    assert obs_connection_failure(Blank())[1] == "Blank"
    for text in (
        "connect call failed",
        "connection refused",
        "timed out",
        "timeout",
        "network is unreachable",
        "no route to host",
        "actively refused",
        "winerror 1225",
    ):
        assert obs_connection_failure(RuntimeError(text))[0] == "down"


def test_make_obs_client_without_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TITAN__OBS__PASSWORD", raising=False)
    monkeypatch.setattr("titan_core.secrets.resolve_secret", lambda *_a, **_k: None)
    assert make_obs_client().password == ""


@pytest.mark.asyncio
async def test_connect_rejects_bad_handshake(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = FakeSocket([json.dumps({"op": 9, "d": {}})])
    client = _install(monkeypatch, sock)
    with pytest.raises(ObsConnectionError, match="expected obs-websocket Hello"):
        await client.connect()

    sock = FakeSocket(
        [
            json.dumps({"op": 0, "d": {"authentication": {"salt": None, "challenge": "c"}}}),
        ]
    )
    client = _install(monkeypatch, sock)
    client.password = "sekrit"
    with pytest.raises(ObsConnectionError, match="missing salt"):
        await client.connect()

    sock = FakeSocket([_hello(), json.dumps({"op": 4, "d": {}})])
    client = _install(monkeypatch, sock)
    with pytest.raises(ObsConnectionError, match="did not accept Identify"):
        await client.connect()


@pytest.mark.asyncio
async def test_connect_wraps_socket_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = FakeSocket([ConnectionResetError("connect call failed")], close_error=OSError("close failed"))
    client = _install(monkeypatch, sock)
    with pytest.raises(ObsConnectionError, match="OBS not running") as raised:
        await client.connect()
    assert raised.value.not_running is True

    async def _boom(*_a: object, **_k: object) -> FakeSocket:
        raise WebSocketException("handshake failed")

    monkeypatch.setattr("titan_core.obs_ws.ws_connect", _boom)
    with pytest.raises(ObsConnectionError, match="handshake failed") as degraded:
        await ObsClient(timeout_s=0.2).connect()
    assert degraded.value.not_running is False


@pytest.mark.asyncio
async def test_close_and_bare_socket_errors() -> None:
    await ObsClient().close()
    client = ObsClient(timeout_s=0.05)
    client._ws = FakeSocket(close_error=WebSocketException("gone"))  # type: ignore[assignment]
    await client.close()
    bare = ObsClient()
    with pytest.raises(ObsConnectionError, match="OBS not running"):
        await bare._send({"op": 6})
    with pytest.raises(ObsConnectionError, match="OBS not running"):
        await bare._recv()

    broken = ObsClient(timeout_s=0.05)
    broken._ws = FakeSocket(send_error=WebSocketException("reset"))  # type: ignore[assignment]
    with pytest.raises(ObsConnectionError, match="reset"):
        await broken.get_version()

    hung = ObsClient(timeout_s=0.05)

    class _Hang:
        async def send(self, _data: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(5)
            return "{}"

        async def close(self) -> None:
            return None

    hung._ws = _Hang()  # type: ignore[assignment]
    with pytest.raises(ObsConnectionError, match="OBS not running"):
        await hung.get_version()

    binary = ObsClient()
    binary._ws = FakeSocket([b"\x00\x01"])  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="non-text"):
        await binary._recv()
    invalid = ObsClient()
    invalid._ws = FakeSocket(["not-json"])  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="invalid JSON"):
        await invalid._recv()
    array = ObsClient()
    array._ws = FakeSocket(["[]"])  # type: ignore[assignment]
    assert await array._recv() == {}


@pytest.mark.asyncio
async def test_request_skips_noise_and_failed_status() -> None:
    def reply(payload: dict[str, Any]) -> list[str]:
        request_id = str(payload["d"]["requestId"])
        return [
            json.dumps({"op": 5, "d": {}}),
            json.dumps({"op": 7, "d": ["nope"]}),
            json.dumps(
                {
                    "op": 7,
                    "d": {
                        "requestId": "other",
                        "requestStatus": {"result": True},
                        "responseData": {},
                    },
                }
            ),
            _frame(request_id, {"obsVersion": "31.0.0"}),
        ]

    client, _sock = _ready(reply)
    assert (await client.get_version())["obsVersion"] == "31.0.0"

    def failed(payload: dict[str, Any]) -> str:
        request_id = str(payload["d"]["requestId"])
        return json.dumps(
            {
                "op": 7,
                "d": {
                    "requestId": request_id,
                    "requestStatus": {"result": False, "comment": 5},
                    "responseData": [],
                },
            }
        )

    client, _sock = _ready(failed)
    with pytest.raises(ObsRequestError, match="unknown") as err:
        await client.request("GetVersion")
    assert err.value.comment is None
    assert err.value.request_type == "GetVersion"

    def commented(payload: dict[str, Any]) -> str:
        return _frame(str(payload["d"]["requestId"]), ok=False, code=203, comment="nope")

    client, _sock = _ready(commented)
    with pytest.raises(ObsRequestError, match="nope"):
        await client.request("GetVersion", {})


@pytest.mark.asyncio
async def test_record_start_and_stop_status_codes() -> None:
    client, sock = _ready(_script({"GetRecordStatus": [_status(active=True, duration=1500)]}))
    await client.start_recording()
    assert [json.loads(raw)["d"]["requestType"] for raw in sock.sent] == ["GetRecordStatus"]
    status = await client.get_record_status()
    assert status.duration_ms == 1500
    assert status.paused is True

    client, _sock = _ready(
        _script(
            {
                "GetRecordStatus": [_status(active=False, duration=True, timecode="00:00:02.000")],
                "StartRecord": [("fail", OUTPUT_RUNNING)],
            }
        )
    )
    await client.start_recording()
    assert (await client.get_record_status()).duration_ms == 2000

    client, _sock = _ready(
        _script(
            {
                "SetRecordDirectory": [("fail", 203, "busy")],
                "GetRecordStatus": [_status(active=False)],
                "StartRecord": [("fail", 400, "denied")],
            }
        )
    )
    with pytest.raises(ObsRequestError, match="denied"):
        await client.start_recording(directory="recordings")

    client, sock = _ready(
        _script({"GetRecordStatus": [_status(active=True)], "StopRecord": [{"outputPath": "a.mkv"}]})
    )
    await client.stop_recording()
    assert "StopRecord" in [json.loads(raw)["d"]["requestType"] for raw in sock.sent]

    client, _sock = _ready(
        _script(
            {
                "GetRecordStatus": [_status(active=True)],
                "StopRecord": [("fail", OUTPUT_NOT_RUNNING)],
            }
        )
    )
    await client.stop_recording()

    client, _sock = _ready(
        _script(
            {
                "GetRecordStatus": [_status(active=True, duration=2.5)],
                "StopRecord": [("fail", 402, "locked")],
            }
        )
    )
    with pytest.raises(ObsRequestError, match="locked"):
        await client.stop_recording()


@pytest.mark.asyncio
async def test_provision_uses_obs_version_alias() -> None:
    client, _sock = _ready(_script({"GetVersion": [{"obs_version": "30.1"}]}))
    plan = await client.provision_titan_profile()
    assert plan["obs_version"] == "30.1"
    assert plan["status"] == "planned"


_CAMERA_ITEMS = {
    "propertyItems": [
        "skip",
        {"itemName": "OBSBOT", "itemValue": "x", "itemEnabled": False},
        {"itemName": 3, "itemValue": "x"},
        {"itemName": "OBSBOT", "itemValue": True},
        {"itemName": "OBSBOT", "itemValue": None},
        {"itemName": "OBSBOT", "itemValue": ""},
        {"itemName": "Integrated", "itemValue": "integrated"},
        {"itemName": "Tiny Cam", "itemValue": "tiny-id"},
        {"itemName": "Other", "itemValue": "obsbot-dev"},
        {"itemName": "OBSBOT Tiny", "itemValue": "second"},
    ]
}


@pytest.mark.asyncio
async def test_select_webcam_reuses_named_input_and_ranks_obsbot() -> None:
    client, sock = _ready(
        _script(
            {
                "GetInputList": [
                    {
                        "inputs": [
                            {"inputName": 1},
                            {"inputName": "Integrated Camera", "inputKind": "dshow_input"},
                            {"inputName": "Pocket Tiny", "inputKind": "v4l2_input"},
                            {"inputName": "Titan Webcam", "inputKind": "dshow_input_custom"},
                        ]
                    }
                ],
                "GetInputPropertiesListPropertyItems": [_CAMERA_ITEMS],
                "SetInputSettings": [{}],
            }
        )
    )
    selected = await client.select_webcam_source()
    assert selected["device_name"] == "Other"
    assert selected["device_id"] == "obsbot-dev"
    settings = json.loads(sock.sent[-1])["d"]["requestData"]
    assert settings["inputName"] == "Titan Webcam"
    assert settings["inputSettings"]["video_device_id"] == "obsbot-dev"


@pytest.mark.asyncio
async def test_select_webcam_skips_duplicate_property_and_failed_apply() -> None:
    client, _sock = _ready(
        _script(
            {
                "GetInputList": [
                    {"inputs": [{"inputName": "Titan Webcam", "inputKind": "wasapi_input_capture"}]}
                ],
                "GetInputPropertiesListPropertyItems": [
                    ("fail", 203, "missing"),
                    {"propertyItems": {}},
                    {"propertyItems": [{"itemName": "Room", "itemValue": "usb-tiny"}]},
                ],
                "SetInputSettings": [("fail", 500, "busy")],
            }
        )
    )
    missed = await client.select_webcam_source()
    assert missed["selected"] is False
    assert missed["input_name"] == "Titan Webcam"


@pytest.mark.asyncio
async def test_select_webcam_scene_fallbacks() -> None:
    client, _sock = _ready(
        _script(
            {
                "GetInputList": [{"inputs": None}],
                "GetSceneList": [
                    {
                        "currentProgramSceneName": "",
                        "scenes": ["x", {"nope": 1}, {"sceneName": ""}, {"sceneName": "Alt"}],
                    }
                ],
                "CreateInput": [("fail", 300, "no dshow"), ("fail", 601, "exists")],
                "GetInputPropertiesListPropertyItems": [
                    {"propertyItems": [{"itemName": "OBSBOT Tiny", "itemValue": "v4l"}]}
                ],
                "SetInputSettings": [{}],
            }
        )
    )
    selected = await client.select_webcam_source()
    assert selected["selected"] is True
    assert selected["input_kind"] == "device_id"

    client, _sock = _ready(
        _script(
            {
                "GetInputList": [{"inputs": []}],
                "GetSceneList": [("fail", 300, "no scenes")],
                "CreateScene": [{}],
                "CreateInput": [("fail", 300, "no")] * 4,
            }
        )
    )
    assert (await client.select_webcam_source())["selected"] is False

    client, _sock = _ready(
        _script(
            {
                "GetInputList": [{"inputs": []}],
                "GetSceneList": [{"scenes": []}],
                "CreateScene": [("fail", 601, "exists")],
                "CreateInput": [("fail", 300, "no")] * 4,
            }
        )
    )
    assert (await client.select_webcam_source())["selected"] is False

    client, _sock = _ready(
        _script(
            {
                "GetInputList": [{"inputs": []}],
                "GetSceneList": [{"scenes": []}],
                "CreateScene": [("fail", 300, "denied")],
            }
        )
    )
    denied = await client.select_webcam_source()
    assert denied == {"selected": False, "detail": "no OBSBOT or Tiny camera in OBS"}


@pytest.mark.asyncio
async def test_select_webcam_creates_on_program_scene_and_matches_device_id() -> None:
    client, _sock = _ready(
        _script(
            {
                "GetInputList": [("fail", 207, "no")],
                "GetSceneList": [{"currentProgramSceneName": "Program"}],
                "CreateInput": [{}],
                "GetInputPropertiesListPropertyItems": [
                    {"propertyItems": [{"itemName": "Facetime", "itemValue": "tiny-cam"}]}
                ],
                "SetInputSettings": [{}],
            }
        )
    )
    picked = await client.select_webcam_source()
    assert picked["selected"] is True
    assert picked["device_name"] == "Facetime"
    assert picked["device_id"] == "tiny-cam"

    client, _sock = _ready(
        _script(
            {
                "GetInputList": [
                    {"inputs": [{"inputName": "Pocket Tiny", "unversionedInputKind": "av_capture_input"}]}
                ],
                "GetInputPropertiesListPropertyItems": [
                    {"propertyItems": [{"itemName": "OBSBOT Tiny", "itemValue": "av-id"}]}
                ],
                "SetInputSettings": [{}],
            }
        )
    )
    picked = await client.select_webcam_source()
    assert picked["device_name"] == "OBSBOT Tiny"
    assert picked["input_kind"] == "device"


@pytest.mark.asyncio
async def test_select_webcam_when_property_list_has_no_obsbot() -> None:
    client, _sock = _ready(
        _script(
            {
                "GetInputList": [{"inputs": [{"inputName": "Titan Webcam", "inputKind": "dshow_input"}]}],
                "GetInputPropertiesListPropertyItems": [
                    {"propertyItems": [{"itemName": "Integrated Camera", "itemValue": "usb"}]}
                ],
            }
        )
    )
    missed = await client.select_webcam_source()
    assert missed == {
        "selected": False,
        "detail": "no OBSBOT or Tiny camera in OBS",
        "input_name": "Titan Webcam",
    }


@pytest.mark.asyncio
async def test_select_webcam_when_no_kind_can_be_created() -> None:
    client, _sock = _ready(
        _script(
            {
                "GetInputList": [{"inputs": []}],
                "GetSceneList": [{"currentProgramSceneName": "Program"}],
                "CreateInput": [("fail", 300, "no")] * 4,
            }
        )
    )
    missed = await client.select_webcam_source()
    assert missed["selected"] is False
    assert "input_name" not in missed
