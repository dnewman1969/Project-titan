"""Hardware-in-the-loop substitute when no game is attached (CI / dev honesty)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from titan_core.logging import get_logger

log = get_logger(__name__)

_STATE: dict[str, Any] = {}


def hil_state() -> dict[str, Any]:
    return dict(_STATE)


class HilDriver:
    """Applies actions to in-memory state and optional trace file (not the real game)."""

    def __init__(self, *, session_id: UUID, trace_path: Path | None, trace: bool) -> None:
        self._session_id = session_id
        self._trace_path = trace_path
        self._trace = trace
        _STATE.clear()
        _STATE["session_id"] = str(session_id)
        _STATE["actions"] = []

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        handled = action_id in {
            "ksp.throttle",
            "ksp.stage",
            "ksp.sas",
            "ksp.rcs",
            "ksp.brake",
            "ksp.brakes",
            "ksp.gear",
            "ksp.steer",
            "ksp.pitch",
            "ksp.yaw",
            "ksp.roll",
            "ksp.fly",
            "ksp.contract.accept",
            "ksp.contract.finish",
            "scs.brake",
            "scs.throttle",
        }
        if not handled:
            return False, f"unknown action {action_id!r}"
        entry = {"action_id": action_id, "params": params}
        actions = _STATE.setdefault("actions", [])
        if not isinstance(actions, list):
            actions = []
            _STATE["actions"] = actions
        actions.append(entry)
        if action_id.startswith("ksp."):
            ksp = _STATE.setdefault("ksp", {})
            if not isinstance(ksp, dict):
                ksp = {}
                _STATE["ksp"] = ksp
            if action_id == "ksp.throttle":
                ksp["throttle"] = float(params.get("throttle", 0.5))
            elif action_id == "ksp.stage":
                ksp["stage_count"] = int(ksp.get("stage_count", 0)) + 1
            elif action_id == "ksp.sas":
                ksp["sas"] = bool(params.get("enabled", True))
            elif action_id == "ksp.rcs":
                ksp["rcs"] = bool(params.get("enabled", True))
            elif action_id in {"ksp.brake", "ksp.brakes"}:
                if "enabled" in params:
                    ksp["brakes"] = bool(params.get("enabled"))
                else:
                    ksp["brakes"] = float(params.get("brake", params.get("fraction", 1.0))) > 0.05
            elif action_id == "ksp.gear":
                ksp["gear"] = bool(params.get("deployed", params.get("enabled", True)))
            elif action_id == "ksp.steer":
                steer = dict(ksp.get("steer") or {})
                for axis in ("pitch", "yaw", "roll"):
                    if axis in params:
                        steer[axis] = max(-1.0, min(1.0, float(params[axis])))
                ksp["steer"] = steer
            elif action_id == "ksp.pitch":
                ksp["pitch"] = max(-1.0, min(1.0, float(params.get("pitch", params.get("value", 0.0)))))
            elif action_id == "ksp.yaw":
                ksp["yaw"] = max(-1.0, min(1.0, float(params.get("yaw", params.get("value", 0.0)))))
            elif action_id == "ksp.roll":
                ksp["roll"] = max(-1.0, min(1.0, float(params.get("roll", params.get("value", 0.0)))))
            elif action_id == "ksp.fly":
                throttle = max(0.0, min(1.0, float(params.get("throttle", 0.0))))
                ksp["throttle"] = throttle
                guided = "pitch_deg" in params and "heading_deg" in params
                ksp["sas"] = False if guided else bool(params.get("sas", True))
                ksp["autopilot"] = guided
                if "pitch_deg" in params:
                    ksp["pitch_deg"] = max(-90.0, min(90.0, float(params["pitch_deg"])))
                if "heading_deg" in params:
                    ksp["heading_deg"] = float(params["heading_deg"]) % 360.0
                if params.get("stage"):
                    ksp["stage_count"] = int(ksp.get("stage_count", 0)) + 1
            elif action_id == "ksp.contract.accept":
                accepted = list(ksp.get("accepted_contracts") or [])
                accepted.append({"type": params.get("type"), "title": params.get("title")})
                ksp["accepted_contracts"] = accepted
            elif action_id == "ksp.contract.finish":
                finished = list(ksp.get("finished_contracts") or [])
                finished.append({"type": params.get("type"), "title": params.get("title")})
                ksp["finished_contracts"] = finished
        if action_id.startswith("scs."):
            scs = _STATE.setdefault("scs", {})
            if not isinstance(scs, dict):
                scs = {}
                _STATE["scs"] = scs
            if action_id == "scs.brake":
                scs["brake"] = float(params.get("brake", params.get("fraction", 1.0)))
            elif action_id == "scs.throttle":
                scs["throttle"] = float(params.get("throttle", 0.5))
        if self._trace and self._trace_path is not None:
            line = json.dumps({"session_id": str(self._session_id), **entry}, separators=(",", ":")) + "\n"
            self._trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self._trace_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        log.info("hil_action", action_id=action_id, params=params)
        return True, None
