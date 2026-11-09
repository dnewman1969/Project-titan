"""OBS Studio client over obs-websocket v5 (shared by API manifest control and capture service)."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect

from titan_core.http import local_client

OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4455


def obs_auth_string(password: str, salt: str, challenge: str) -> str:
    """obs-websocket v5 authentication string (base64 SHA-256 chain)."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode("utf-8")).digest())
    return base64.b64encode(hashlib.sha256(secret + challenge.encode("utf-8")).digest()).decode("ascii")


@dataclass(frozen=True, slots=True)
class ObsRecordStatus:
    active: bool
    paused: bool
    duration_ms: int | None = None


class ObsClient:
    """Minimal obs-websocket v5 client: handshake, version, record control, status."""

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
        self._ws = await ws_connect(self.ws_url, open_timeout=self.timeout_s)
        hello = await self._recv()
        if hello.get("op") != OP_HELLO:
            msg = "expected obs-websocket Hello"
            raise RuntimeError(msg)
        hello_d = hello.get("d")
        auth_info = hello_d.get("authentication") if isinstance(hello_d, dict) else None
        identify_d: dict[str, Any] = {"rpcVersion": 1}
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

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

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
                raise RuntimeError(f"obs request {request_type!r} failed ({code})")
            response = data.get("responseData")
            return response if isinstance(response, dict) else {}

    async def get_version(self) -> dict[str, Any]:
        return await self.request("GetVersion")

    async def get_record_status(self) -> ObsRecordStatus:
        body = await self.request("GetRecordStatus")
        active = bool(body.get("outputActive"))
        paused = bool(body.get("outputPaused"))
        timecode = body.get("outputTimecode")
        duration_ms = int(timecode) if isinstance(timecode, (int, float)) else None
        return ObsRecordStatus(active=active, paused=paused, duration_ms=duration_ms)

    async def start_recording(self) -> None:
        await self.request("StartRecord")

    async def stop_recording(self) -> None:
        await self.request("StopRecord")

    async def provision_titan_profile(self) -> dict[str, str]:
        """Best-effort Titan profile plan; full scene graph is a later M8 slice."""
        version = await self.get_version()
        obs_version = str(version.get("obsVersion") or version.get("obs_version") or "unknown")
        return {
            "profile": "Titan",
            "collection": "Titan",
            "scene": "Titan Gameplay",
            "status": "planned",
            "obs_version": obs_version,
        }

    async def probe_http(self) -> bool:
        """True when something answers HTTP on the obs-websocket port (usually 426)."""
        url = f"http://{self.host}:{self.port}/"
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.get(url)
        return response.status_code in {200, 400, 426}

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            msg = "not connected"
            raise RuntimeError(msg)
        await self._ws.send(json.dumps(payload))

    async def _recv(self) -> dict[str, Any]:
        if self._ws is None:
            msg = "not connected"
            raise RuntimeError(msg)
        raw = await self._ws.recv()
        if not isinstance(raw, str):
            msg = "obs-websocket returned non-text frame"
            raise RuntimeError(msg)
        body = json.loads(raw)
        return body if isinstance(body, dict) else {}


def make_obs_client() -> ObsClient:
    """Build a client from TitanConfig.obs (host/port/password via yaml + TITAN__OBS__*)."""
    from titan_core.config import load_config

    obs = load_config().obs
    password = obs.password.get_secret_value() if obs.password is not None else ""
    return ObsClient(host=obs.host, port=obs.port, password=password, timeout_s=obs.timeout_s)
