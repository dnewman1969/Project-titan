"""OBS Studio client over obs-websocket v5 (shared by API manifest control and capture service)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import WebSocketException

OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4455

# obs-websocket RequestStatus codes that mean the output is already in the requested state.
OUTPUT_RUNNING = 500
OUTPUT_NOT_RUNNING = 501
RESOURCE_ALREADY_EXISTS = 601

WEBCAM_INPUT_NAME = "Titan Webcam"
# USB names containing either token are the OBSBOT Tiny family (case-insensitive).
_CAMERA_HINTS = ("obsbot", "tiny")
# (inputKind, device property) for Windows DirectShow, Linux V4L2, and macOS AVFoundation.
_CAPTURE_KINDS: tuple[tuple[str, str], ...] = (
    ("dshow_input", "video_device_id"),
    ("v4l2_input", "device_id"),
    ("av_capture_input", "device"),
    ("av_capture_input_v2", "device"),
)


def obs_auth_string(password: str, salt: str, challenge: str) -> str:
    """obs-websocket v5 authentication string (base64 SHA-256 chain)."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode("utf-8")).digest())
    return base64.b64encode(hashlib.sha256(secret + challenge.encode("utf-8")).digest()).decode("ascii")


def camera_name_matches(name: str) -> bool:
    """True when a USB / OBS device name contains OBSBOT or Tiny."""
    folded = name.casefold()
    return any(hint in folded for hint in _CAMERA_HINTS)


def timecode_to_ms(value: object) -> int | None:
    """OBS `outputTimecode` as milliseconds. Accepts a number or `HH:MM:SS.mmm`."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return int((hours * 3600 + minutes * 60 + seconds) * 1000)
        if len(parts) == 4:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            frames = int(parts[3])
            return (hours * 3600 + minutes * 60 + seconds) * 1000 + frames
    except ValueError:
        return None
    return None


def obs_connection_failure(exc: BaseException) -> tuple[str, str]:
    """Map a connect/read failure to `(state, detail)`. `down` means OBS is not running."""
    if _is_not_running(exc):
        return "down", "OBS not running"
    text = str(exc).strip() or type(exc).__name__
    return "degraded", text


def _is_not_running(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError | ConnectionRefusedError):
        return True
    errno = getattr(exc, "errno", None)
    if errno in {111, 61, 10061}:
        return True
    text = str(exc).casefold()
    needles = (
        "connect call failed",
        "connection refused",
        "timed out",
        "timeout",
        "network is unreachable",
        "no route to host",
        "actively refused",
        "winerror 1225",
    )
    return any(needle in text for needle in needles)


class ObsError(RuntimeError):
    """OBS client failure (connection or request)."""


class ObsConnectionError(ObsError):
    """The websocket never became a usable obs-websocket v5 session."""

    def __init__(self, detail: str, *, not_running: bool) -> None:
        super().__init__(detail)
        self.detail = detail
        self.not_running = not_running


class ObsRequestError(ObsError):
    """obs-websocket returned `requestStatus.result == false`."""

    def __init__(self, request_type: str, code: object, comment: str | None = None) -> None:
        self.request_type = request_type
        self.code = code
        self.comment = comment
        detail = f"obs request {request_type!r} failed ({code})"
        if comment:
            detail = f"{detail}: {comment}"
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ObsRecordStatus:
    active: bool
    paused: bool
    duration_ms: int | None = None


class ObsClient:
    """Minimal obs-websocket v5 client: handshake, version, record control, webcam source."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        password: str = "",
        timeout_s: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout_s = timeout_s
        self._ws: ClientConnection | None = None

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def connect(self) -> None:
        """Complete the obs-websocket v5 Identify handshake.

        Compression is disabled: OBS rejects or drops clients that offer permessage-deflate,
        which otherwise leaves `GET /capture/obs` at HTTP 200 with `connected: false`.
        """
        try:
            # websockets enables permessage-deflate by default; obs-websocket does not negotiate it.
            self._ws = await ws_connect(
                self.ws_url,
                open_timeout=self.timeout_s,
                compression=None,
                max_size=2**20,
            )
            hello = await self._recv()
            if hello.get("op") != OP_HELLO:
                msg = "expected obs-websocket Hello"
                raise RuntimeError(msg)
            hello_d = hello.get("d")
            auth_info = hello_d.get("authentication") if isinstance(hello_d, dict) else None
            identify_d: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
            if isinstance(auth_info, dict):
                if not self.password:
                    msg = "OBS websocket authentication required; set TITAN__OBS__PASSWORD"
                    raise RuntimeError(msg)
                salt = auth_info.get("salt")
                challenge = auth_info.get("challenge")
                if not isinstance(salt, str) or not isinstance(challenge, str):
                    msg = "OBS Hello authentication missing salt/challenge"
                    raise RuntimeError(msg)
                identify_d["authentication"] = obs_auth_string(self.password, salt, challenge)
            await self._send({"op": OP_IDENTIFY, "d": identify_d})
            identified = await self._recv()
            if identified.get("op") != OP_IDENTIFIED:
                msg = "obs-websocket did not accept Identify"
                raise RuntimeError(msg)
        except ObsConnectionError:
            await self.close()
            raise
        except (OSError, WebSocketException, RuntimeError) as exc:
            await self.close()
            state, detail = obs_connection_failure(exc)
            raise ObsConnectionError(detail, not_running=state == "down") from exc

    async def close(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is None:
            return
        try:
            await ws.close()
        except (OSError, WebSocketException):
            return

    async def request(self, request_type: str, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        payload: dict[str, Any] = {"requestType": request_type, "requestId": request_id}
        if request_data is not None:
            payload["requestData"] = request_data
        await self._send({"op": OP_REQUEST, "d": payload})
        while True:
            message = await self._recv()
            if message.get("op") != OP_REQUEST_RESPONSE:
                continue
            data = message.get("d")
            if not isinstance(data, dict) or data.get("requestId") != request_id:
                continue
            status = data.get("requestStatus")
            if isinstance(status, dict) and status.get("result") is False:
                code = status.get("code", "unknown")
                comment = status.get("comment")
                raise ObsRequestError(
                    request_type,
                    code,
                    comment if isinstance(comment, str) else None,
                )
            response = data.get("responseData")
            return response if isinstance(response, dict) else {}

    async def get_version(self) -> dict[str, Any]:
        return await self.request("GetVersion")

    async def get_record_status(self) -> ObsRecordStatus:
        body = await self.request("GetRecordStatus")
        active = bool(body.get("outputActive"))
        paused = bool(body.get("outputPaused"))
        duration = body.get("outputDuration")
        if isinstance(duration, int | float) and not isinstance(duration, bool):
            duration_ms: int | None = int(duration)
        else:
            duration_ms = timecode_to_ms(body.get("outputTimecode"))
        return ObsRecordStatus(active=active, paused=paused, duration_ms=duration_ms)

    async def start_recording(self, *, directory: str | None = None) -> None:
        """StartRecord. A directory is applied with SetRecordDirectory when OBS accepts it."""
        if directory:
            await self._try_request("SetRecordDirectory", {"recordDirectory": directory})
        status = await self.get_record_status()
        if status.active:
            return
        try:
            await self.request("StartRecord")
        except ObsRequestError as exc:
            if exc.code == OUTPUT_RUNNING:
                return
            raise

    async def stop_recording(self) -> None:
        status = await self.get_record_status()
        if not status.active:
            return
        try:
            await self.request("StopRecord")
        except ObsRequestError as exc:
            if exc.code == OUTPUT_NOT_RUNNING:
                return
            raise

    async def provision_titan_profile(self) -> dict[str, str]:
        """Best-effort Titan profile plan; scene items are created by `select_webcam_source`."""
        version = await self.get_version()
        obs_version = str(version.get("obsVersion") or version.get("obs_version") or "unknown")
        return {
            "profile": "Titan",
            "collection": "Titan",
            "scene": "Titan Gameplay",
            "status": "planned",
            "obs_version": obs_version,
        }

    async def select_webcam_source(self) -> dict[str, Any]:
        """Select a camera whose OBS device name contains OBSBOT or Tiny.

        Reuses an input named for that camera (or `Titan Webcam`). Does not retarget unrelated
        capture devices. Creates `Titan Webcam` on the current program scene when OBS is the
        capture path and no matching input exists yet.
        """
        inputs = await self._input_list()
        target = _find_target_input(inputs)
        if target is None:
            scene = await self._scene_for_new_input()
            if scene is None:
                return _webcam_miss()
            created_kind: str | None = None
            for kind, _prop in _CAPTURE_KINDS:
                if await self._try_create_input(scene, kind):
                    created_kind = kind
                    break
            if created_kind is None:
                return _webcam_miss()
            target = {"inputName": WEBCAM_INPUT_NAME, "inputKind": created_kind}
        name = target.get("inputName")
        if not isinstance(name, str) or not name:
            return _webcam_miss()
        kind = str(target.get("inputKind") or target.get("unversionedInputKind") or "")
        known_prop = _property_for_kind(kind)
        props = [known_prop] if known_prop is not None else [prop for _kind, prop in _CAPTURE_KINDS]
        seen: set[str] = set()
        for prop in props:
            if prop in seen:
                continue
            seen.add(prop)
            selected = await self._select_on_input(name, prop)
            if selected is not None:
                return selected
        return _webcam_miss(input_name=name)

    async def probe_http(self) -> bool:
        """True when something answers HTTP on the obs-websocket port (usually 426)."""
        from titan_core.http import local_client

        url = f"http://{self.host}:{self.port}/"
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.get(url)
        return response.status_code in {200, 400, 426}

    async def _input_list(self) -> list[dict[str, Any]]:
        try:
            data = await self.request("GetInputList")
        except ObsRequestError:
            return []
        raw = data.get("inputs")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    async def _scene_for_new_input(self) -> str | None:
        try:
            data = await self.request("GetSceneList")
        except ObsRequestError:
            data = {}
        current = data.get("currentProgramSceneName")
        if isinstance(current, str) and current:
            return current
        scenes = data.get("scenes")
        if isinstance(scenes, list):
            for scene in scenes:
                if isinstance(scene, dict):
                    scene_name = scene.get("sceneName")
                    if isinstance(scene_name, str) and scene_name:
                        return scene_name
        try:
            await self.request("CreateScene", {"sceneName": "Titan Gameplay"})
        except ObsRequestError as exc:
            if exc.code != RESOURCE_ALREADY_EXISTS:
                return None
        return "Titan Gameplay"

    async def _try_create_input(self, scene: str, kind: str) -> bool:
        try:
            await self.request(
                "CreateInput",
                {
                    "sceneName": scene,
                    "inputName": WEBCAM_INPUT_NAME,
                    "inputKind": kind,
                    "inputSettings": {},
                    "sceneItemEnabled": True,
                },
            )
        except ObsRequestError as exc:
            return exc.code == RESOURCE_ALREADY_EXISTS
        return True

    async def _select_on_input(self, input_name: str, property_name: str) -> dict[str, Any] | None:
        try:
            listed = await self.request(
                "GetInputPropertiesListPropertyItems",
                {"inputName": input_name, "propertyName": property_name},
            )
        except ObsRequestError:
            return None
        items = listed.get("propertyItems")
        if not isinstance(items, list):
            return None
        match = _best_camera_item(items)
        if match is None:
            return None
        device_name, device_id = match
        try:
            await self.request(
                "SetInputSettings",
                {
                    "inputName": input_name,
                    "inputSettings": {property_name: device_id},
                    "overlay": True,
                },
            )
        except ObsRequestError:
            return None
        return {
            "selected": True,
            "input_name": input_name,
            "input_kind": property_name,
            "device_name": device_name,
            "device_id": device_id,
            "detail": f"OBS source {input_name} → {device_name}",
        }

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise ObsConnectionError("OBS not running", not_running=True)
        try:
            await self._ws.send(json.dumps(payload))
        except (OSError, WebSocketException) as exc:
            state, detail = obs_connection_failure(exc)
            raise ObsConnectionError(detail, not_running=state == "down") from exc

    async def _recv(self) -> dict[str, Any]:
        if self._ws is None:
            raise ObsConnectionError("OBS not running", not_running=True)
        try:
            raw = await asyncio.wait_for(self._ws.recv(), self.timeout_s)
        except (OSError, WebSocketException) as exc:
            state, detail = obs_connection_failure(exc)
            raise ObsConnectionError(detail, not_running=state == "down") from exc
        if not isinstance(raw, str):
            msg = "obs-websocket returned non-text frame"
            raise RuntimeError(msg)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = "obs-websocket returned invalid JSON"
            raise RuntimeError(msg) from exc
        return body if isinstance(body, dict) else {}

    async def _try_request(self, request_type: str, request_data: dict[str, Any]) -> bool:
        try:
            await self.request(request_type, request_data)
        except ObsRequestError:
            return False
        return True


def _property_for_kind(kind: str) -> str | None:
    for known, prop in _CAPTURE_KINDS:
        if kind == known or kind.startswith(known):
            return prop
    return None


def _find_target_input(inputs: list[dict[str, Any]]) -> dict[str, Any] | None:
    named: dict[str, Any] | None = None
    for item in inputs:
        name = item.get("inputName")
        if not isinstance(name, str):
            continue
        if name == WEBCAM_INPUT_NAME:
            return item
        if named is None and camera_name_matches(name):
            named = item
    return named


def _best_camera_item(items: list[Any]) -> tuple[str, str] | None:
    ranked: list[tuple[int, str, str]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("itemEnabled") is False:
            continue
        name = item.get("itemName")
        value = item.get("itemValue")
        if not isinstance(name, str):
            continue
        if isinstance(value, bool) or value is None:
            continue
        device_id = str(value)
        if not device_id:
            continue
        if not camera_name_matches(name) and not camera_name_matches(device_id):
            continue
        rank = 0 if "obsbot" in name.casefold() or "obsbot" in device_id.casefold() else 1
        ranked.append((rank, name, device_id))
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0])
    _rank, name, device_id = ranked[0]
    return name, device_id


def _webcam_miss(*, input_name: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "selected": False,
        "detail": "no OBSBOT or Tiny camera in OBS",
    }
    if input_name is not None:
        body["input_name"] = input_name
    return body


def make_obs_client() -> ObsClient:
    """Build a client from TitanConfig.obs (host/port/password via yaml, env, or keyring)."""
    from titan_core.config import load_config
    from titan_core.secrets import resolve_secret

    obs = load_config().obs
    secret = resolve_secret(obs.password, "obs")
    password = secret.get_secret_value() if secret is not None else ""
    return ObsClient(host=obs.host, port=obs.port, password=password, timeout_s=obs.timeout_s)
