"""Kerbal Space Program control through kRPC.

Thrust (throttle), staging, SAS/RCS, brakes/gear, and pitch/yaw/roll steering.
Tests inject `connect_fn` so Linux CI never needs a live kRPC server.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from titan_core.logging import get_logger

log = get_logger(__name__)

_CONN_LOCK = threading.Lock()
_CONN: Any = None
_CONN_KEY: tuple[str, int, int] | None = None

ConnectFn = Callable[[str, int, int], Any]


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp_axis(value: float) -> float:
    return max(-1.0, min(1.0, value))


class KrpcDriver:
    def __init__(
        self,
        *,
        host: str,
        rpc_port: int,
        stream_port: int,
        connect_fn: ConnectFn | None = None,
    ) -> None:
        self._host = host
        self._rpc_port = rpc_port
        self._stream_port = stream_port
        self._connect_fn = connect_fn or _connect

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            conn = self._connect_fn(self._host, self._rpc_port, self._stream_port)
        except Exception as exc:
            return False, f"krpc connect failed: {exc}"
        try:
            vessel = conn.space_center.active_vessel
            if vessel is None:
                return False, "krpc: no active vessel (not in flight?)"
            control = vessel.control
            if action_id == "ksp.throttle":
                value = float(params.get("throttle", 0.5))
                control.throttle = _clamp01(value)
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
            if action_id in {"ksp.brake", "ksp.brakes"}:
                if "enabled" in params:
                    control.brakes = bool(params.get("enabled"))
                else:
                    brakes = _clamp01(float(params.get("brake", params.get("fraction", 1.0))))
                    control.brakes = brakes > 0.05
                return True, None
            if action_id == "ksp.gear":
                control.gear = bool(params.get("deployed", params.get("enabled", True)))
                return True, None
            if action_id == "ksp.steer":
                if "pitch" in params:
                    control.pitch = _clamp_axis(float(params["pitch"]))
                if "yaw" in params:
                    control.yaw = _clamp_axis(float(params["yaw"]))
                if "roll" in params:
                    control.roll = _clamp_axis(float(params["roll"]))
                if not any(k in params for k in ("pitch", "yaw", "roll")):
                    return False, "ksp.steer requires pitch, yaw, and/or roll"
                return True, None
            if action_id == "ksp.pitch":
                control.pitch = _clamp_axis(float(params.get("pitch", params.get("value", 0.0))))
                return True, None
            if action_id == "ksp.yaw":
                control.yaw = _clamp_axis(float(params.get("yaw", params.get("value", 0.0))))
                return True, None
            if action_id == "ksp.roll":
                control.roll = _clamp_axis(float(params.get("roll", params.get("value", 0.0))))
                return True, None
            return False, f"unknown ksp action {action_id!r}"
        except Exception as exc:
            return False, f"krpc: {exc}"

    def reset(self) -> None:
        """Neutralize steering axes and cut throttle when possible (session/kill hygiene)."""
        try:
            conn = self._connect_fn(self._host, self._rpc_port, self._stream_port)
            vessel = conn.space_center.active_vessel
            if vessel is None:
                return
            control = vessel.control
            control.throttle = 0.0
            control.pitch = 0.0
            control.yaw = 0.0
            control.roll = 0.0
        except Exception as exc:
            log.warning("krpc_reset_failed", err=str(exc))
