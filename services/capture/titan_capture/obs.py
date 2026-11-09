"""OBS Studio client over obs-websocket v5 (M8.T1 stub).

Production control uses WebSocket RPC on port 4455. HTTP GET on the same port returns
426 Upgrade Required; that probe is covered by respx tests and matches what `check_obs` expects.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect

from titan_core.http import local_client

OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4455


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
        if hello.get("op") != 0:
            msg = "expected obs-websocket Hello"
            raise RuntimeError(msg)
        await self._send({"op": OP_IDENTIFY, "d": {"rpcVersion": 1, "authentication": self.password}})
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
        """Idempotent profile/scene provisioning is M8 follow-up; returns a stub plan."""
        return {
            "profile": "Titan",
            "collection": "Titan",
            "scene": "Titan Gameplay",
            "status": "stub",
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
