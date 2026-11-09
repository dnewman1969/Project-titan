"""ETS2 / ATS control: virtual XInput (ViGEm) with keyboard fallback on Windows."""

from __future__ import annotations

import sys
from typing import Any

from titan_core.logging import get_logger

log = get_logger(__name__)


class ScsDriver:
    def __init__(self) -> None:
        self._pad: Any = None
        self._mode: str | None = None

    def _ensure_pad(self) -> tuple[bool, str | None]:
        if self._pad is not None:
            return True, None
        if sys.platform != "win32":
            return False, "scs virtual gamepad requires Windows (use TITAN_PLAY_BACKEND=hil on Linux)"
        try:
            import vgamepad as vg

            self._pad = vg.VX360Gamepad()
            self._mode = "vgamepad"
            return True, None
        except Exception as exc:
            log.warning("vgamepad_unavailable", err=str(exc))
        return self._keyboard_ready()

    def _keyboard_ready(self) -> tuple[bool, str | None]:
        self._mode = "keyboard"
        return True, None

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        ok, err = self._ensure_pad()
        if not ok:
            return False, err
        if action_id == "scs.brake":
            fraction = max(0.0, min(1.0, float(params.get("brake", params.get("fraction", 1.0)))))
            if self._mode == "vgamepad" and self._pad is not None:
                self._pad.left_trigger_float(value_float=fraction)
                self._pad.update()
                return True, None
            return self._keyboard_brake(fraction)
        if action_id == "scs.throttle":
            fraction = max(0.0, min(1.0, float(params.get("throttle", 0.5))))
            if self._mode == "vgamepad" and self._pad is not None:
                self._pad.right_trigger_float(value_float=fraction)
                self._pad.update()
                return True, None
            return False, "scs.throttle needs virtual gamepad (ViGEm)"
        return False, f"unknown scs action {action_id!r}"

    def _keyboard_brake(self, fraction: float) -> tuple[bool, str | None]:
        from titan_actions.win_input import key_hold

        hold_s = max(0.05, min(1.5, fraction))
        try:
            key_hold(0x53, hold_s=hold_s)  # 'S' — default ETS2/ATS brake
            return True, None
        except Exception as exc:
            return False, f"keyboard brake failed: {exc}"
