"""Kerbal Space Program control through kRPC."""

from __future__ import annotations

import threading
from typing import Any

from titan_core.logging import get_logger

log = get_logger(__name__)

_CONN_LOCK = threading.Lock()
_CONN: Any = None
_CONN_KEY: tuple[str, int, int] | None = None


def _connect(host: str, rpc_port: int, stream_port: int) -> Any:
    global _CONN, _CONN_KEY
    key = (host, rpc_port, stream_port)
    with _CONN_LOCK:
        if _CONN is not None and key == _CONN_KEY:
            return _CONN
        import krpc

        _CONN = krpc.connect(
            name="Titan",
            address=host,
            rpc_port=rpc_port,
            stream_port=stream_port,
        )
        _CONN_KEY = key
        log.info("krpc_connected", host=host, rpc_port=rpc_port)
        return _CONN


class KrpcDriver:
    def __init__(self, *, host: str, rpc_port: int, stream_port: int) -> None:
        self._host = host
        self._rpc_port = rpc_port
        self._stream_port = stream_port

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            conn = _connect(self._host, self._rpc_port, self._stream_port)
        except Exception as exc:
            return False, f"krpc connect failed: {exc}"
        try:
            vessel = conn.space_center.active_vessel
            if vessel is None:
                return False, "krpc: no active vessel (not in flight?)"
            control = vessel.control
            if action_id == "ksp.throttle":
                value = float(params.get("throttle", 0.5))
                control.throttle = max(0.0, min(1.0, value))
                return True, None
            if action_id == "ksp.stage":
                control.activate_next_stage()
                return True, None
            if action_id == "ksp.sas":
                control.sas = bool(params.get("enabled", True))
                return True, None
            if action_id == "ksp.rcs":
                control.rcs = bool(params.get("enabled", True))
                return True, None
            if action_id == "ksp.brake":
                brakes = max(0.0, min(1.0, float(params.get("brake", params.get("fraction", 1.0)))))
                control.brakes = brakes > 0.05
                return True, None
            return False, f"unknown ksp action {action_id!r}"
        except Exception as exc:
            return False, f"krpc: {exc}"
