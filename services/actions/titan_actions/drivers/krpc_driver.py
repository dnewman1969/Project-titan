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
            if action_id in {"ksp.contract.accept", "ksp.contract.finish"}:
                return _contract_action(conn, action_id, params)
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
            if action_id == "ksp.fly":
                return _apply_fly(conn, vessel, control, params)
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
            _disengage_autopilot(vessel)
        except Exception as exc:
            log.warning("krpc_reset_failed", err=str(exc))


def _apply_fly(conn: Any, vessel: Any, control: Any, params: dict[str, Any]) -> tuple[bool, str | None]:
    """Hold throttle plus either the kRPC autopilot (pitch/heading) or SAS.

    kRPC cannot run SAS and the autopilot together. A heading target engages
    ``auto_pilot`` in the surface frame (the tutorial's ``target_pitch_and_heading``)
    with a slow stopping time so a tall rocket does not hunt itself into a tumble.
    Without a target, SAS stays on (stability assist, unless ``sas_mode`` says
    otherwise) so rotation can damp. Throttle is applied after staging so a
    launch stage does not leave the engines at zero.
    """
    if params.get("stage"):
        control.activate_next_stage()
    control.throttle = _clamp01(float(params.get("throttle", 0.0)))
    pitch = params.get("pitch_deg")
    heading = params.get("heading_deg")
    autopilot = getattr(vessel, "auto_pilot", None)
    if pitch is not None and heading is not None and autopilot is not None:
        try:
            control.sas = False
            reference = getattr(vessel, "surface_reference_frame", None)
            if reference is not None:
                autopilot.reference_frame = reference
            _steady_autopilot(autopilot)
            autopilot.target_pitch_and_heading(
                max(-90.0, min(90.0, float(pitch))),
                float(heading) % 360.0,
            )
            engage = getattr(autopilot, "engage", None)
            if callable(engage):
                engage()
            return True, None
        except Exception as exc:
            log.warning("krpc_autopilot_failed", err=str(exc))
            try:
                control.sas = True
                _apply_sas_mode(conn, control, "stability")
            except Exception as sas_exc:
                log.warning("krpc_sas_fallback_failed", err=str(sas_exc))
            return True, None
    _disengage_autopilot(vessel)
    control.sas = bool(params.get("sas", True))
    if control.sas:
        _apply_sas_mode(conn, control, params.get("sas_mode") or "stability")
    return True, None


def _steady_autopilot(autopilot: Any) -> None:
    """Ease kRPC's default gains. A short stopping time over-corrects and tumbles.

    ``stopping_time`` is how long the autopilot allows itself to kill the
    rotation; larger is gentler. ``attenuation_angle`` (degrees) is where it
    stops cranking the controls. ``target_roll`` keeps the craft wings-level.
    """
    for name, value in (
        # One value per axis (pitch, roll, yaw). The default 0.5 s hunts.
        ("stopping_time", (2.0, 2.0, 2.0)),
        ("attenuation_angle", (1.0, 1.0, 1.0)),
        ("target_roll", 0.0),
    ):
        try:
            setattr(autopilot, name, value)
        except Exception as exc:
            log.warning("krpc_autopilot_gain_failed", gain=name, err=str(exc))


def _apply_sas_mode(conn: Any, control: Any, mode: object) -> None:
    if not isinstance(mode, str) or not mode.strip():
        return
    enum_name = {"stability": "stability_assist", "prograde": "prograde"}.get(mode.strip(), mode.strip())
    center = getattr(conn, "space_center", None)
    enum = getattr(center, "SASMode", None)
    value = getattr(enum, enum_name, None) if enum is not None else None
    if value is None:
        return
    try:
        control.sas_mode = value
    except Exception as exc:
        log.warning("krpc_sas_mode_failed", mode=enum_name, err=str(exc))


def _contract_action(conn: Any, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
    """Accept an offered contract, or finish / recover one whose parameters are done.

    Stock kRPC's Contract type has ``accept``. It does not have a turn-in method.
    When ``complete`` (or ``finish`` / ``turn_in``) exists it is called. A recover
    parameter on the ground calls ``vessel.recover``. Otherwise the game marks the
    contract complete on its own once every parameter is done, and this returns
    success without inventing a button.
    """
    try:
        center = conn.space_center
    except Exception as exc:
        return False, f"krpc: no space center ({exc})"
    if action_id == "ksp.contract.accept":
        contract = _find_contract(center, params, ("offered_contracts", "active_contracts"))
        if contract is None:
            return False, "krpc: offered contract not found"
        if _state_name(contract) == "active":
            return True, None
        _set_seen(contract)
        accept = getattr(contract, "accept", None)
        if not callable(accept):
            return False, "krpc: contract has no accept()"
        try:
            accept()
        except Exception as exc:
            return False, f"krpc: accept failed: {exc}"
        return True, None
    contract = _find_contract(
        center,
        params,
        ("active_contracts", "completed_contracts", "offered_contracts"),
    )
    if contract is None:
        return False, "krpc: contract not found to finish"
    if _state_name(contract) == "completed":
        return True, None
    for method_name in ("complete", "finish", "turn_in"):
        try:
            method = getattr(contract, method_name)
        except Exception as exc:
            log.info("krpc_contract_method_unavailable", method=method_name, err=str(exc))
            continue
        if not callable(method):
            continue
        try:
            method()
        except Exception as exc:
            message = str(exc).lower()
            if any(token in message for token in ("not found", "unknown", "no such", "has no")):
                continue
            return False, f"krpc: {method_name} failed: {exc}"
        return True, None
    vessel = getattr(center, "active_vessel", None)
    if _needs_recover(contract) and vessel is not None and _on_ground(vessel):
        recover = getattr(vessel, "recover", None)
        if callable(recover):
            try:
                recover()
            except Exception as exc:
                return False, f"krpc: recover failed: {exc}"
            return True, None
    if _parameters_done(contract):
        return True, None
    if _needs_recover(contract):
        return False, "krpc: vessel is not on the ground to recover"
    return False, "krpc: contract is not ready to finish"


def _find_contract(center: Any, params: dict[str, Any], buckets: tuple[str, ...]) -> Any:
    manager = getattr(center, "contract_manager", None)
    if manager is None:
        return None
    want_type = str(params.get("type") or "").strip().lower()
    want_title = str(params.get("title") or "").strip().lower()
    if not want_title:
        return None
    for bucket in buckets:
        for contract in _contract_bucket(manager, bucket):
            title = str(getattr(contract, "title", "") or "").strip().lower()
            ctype = str(getattr(contract, "type", "") or "").strip().lower()
            if title == want_title and (not want_type or ctype == want_type):
                return contract
    return None


def _contract_bucket(manager: Any, name: str) -> list[Any]:
    try:
        value = getattr(manager, name)
        if callable(value):
            value = value()
        if value is None:
            return []
        return list(value)
    except Exception:
        return []


def _set_seen(contract: Any) -> None:
    try:
        seen = getattr(contract, "seen", None)
        if seen is False:
            contract.seen = True
    except Exception as exc:
        log.warning("krpc_contract_seen_failed", err=str(exc))


def _state_name(contract: Any) -> str:
    try:
        state = getattr(contract, "state", None)
    except Exception:
        return ""
    name = getattr(state, "name", None)
    if isinstance(name, str) and name:
        return name.strip().lower()
    text = str(state or "")
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.strip().lower()


def _needs_recover(contract: Any) -> bool:
    for param in _leaf_parameters(contract):
        if _param_flag(param, "completed") or _param_flag(param, "optional"):
            continue
        text = f"{getattr(param, 'title', '')} {getattr(param, 'notes', '')}".lower()
        if "recover" in text:
            return True
    return False


def _parameters_done(contract: Any) -> bool:
    required = [param for param in _leaf_parameters(contract) if not _param_flag(param, "optional")]
    return bool(required) and all(_param_flag(param, "completed") for param in required)


def _leaf_parameters(contract: Any) -> list[Any]:
    try:
        nodes = getattr(contract, "parameters", None)
        if callable(nodes):
            nodes = nodes()
        pending = list(nodes or [])
    except Exception:
        return []
    leaves: list[Any] = []
    while pending:
        node = pending.pop(0)
        try:
            children = getattr(node, "children", None)
            if callable(children):
                children = children()
            child_list = list(children or [])
        except Exception:
            child_list = []
        if child_list:
            pending = child_list + pending
            continue
        leaves.append(node)
    return leaves


def _param_flag(param: Any, name: str) -> bool:
    try:
        return bool(getattr(param, name, False))
    except Exception:
        return False


def _on_ground(vessel: Any) -> bool:
    try:
        situation = getattr(vessel, "situation", None)
    except Exception:
        return False
    name = getattr(situation, "name", None)
    text = name if isinstance(name, str) and name else str(situation or "")
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.strip().lower() in {"landed", "splashed", "pre_launch"}


def _disengage_autopilot(vessel: Any) -> None:
    autopilot = getattr(vessel, "auto_pilot", None)
    disengage = getattr(autopilot, "disengage", None)
    if not callable(disengage):
        return
    try:
        disengage()
    except Exception as exc:
        log.warning("krpc_autopilot_disengage_failed", err=str(exc))
