"""ETS2 / ATS control: virtual XInput (ViGEm) with keyboard fallback on Windows.

Agents do not need a physical pad. Preferred path is ViGEmBus virtual X360;
when ViGEm is unavailable (or TITAN_PLAY_BACKEND=keyboard), SendInput holds
W/S for throttle/brake. Tests inject pad_factory / key_hold_fn so Linux CI
can exercise the same code without ViGEm.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, Protocol

from titan_core.logging import get_logger

log = get_logger(__name__)

VK_S = 0x53  # default ETS2/ATS brake
VK_W = 0x57  # default ETS2/ATS throttle


class KeyHoldFn(Protocol):
    def __call__(self, vk: int, *, hold_s: float) -> None: ...


class ScsDriver:
    def __init__(
        self,
        *,
        prefer_keyboard: bool = False,
        pad_factory: Callable[[], Any] | None = None,
        key_hold_fn: KeyHoldFn | None = None,
    ) -> None:
        self._prefer_keyboard = prefer_keyboard
        self._pad_factory = pad_factory
        self._key_hold_fn = key_hold_fn
        self._pad: Any = None
        self._mode: str | None = None

    @property
    def mode(self) -> str | None:
        return self._mode

    def _ensure_pad(self) -> tuple[bool, str | None]:
        if self._mode is not None:
            return True, None
        if self._prefer_keyboard:
            return self._keyboard_ready()
        if self._pad_factory is not None:
            try:
                self._pad = self._pad_factory()
                self._mode = "vgamepad"
                return True, None
            except Exception as exc:
                log.warning("pad_factory_failed", err=str(exc))
                return self._keyboard_ready()
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
        if sys.platform != "win32" and self._key_hold_fn is None:
            return False, "scs keyboard play requires Windows SendInput (use TITAN_PLAY_BACKEND=hil on Linux)"
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
            return self._keyboard_axis(VK_S, fraction, label="brake")
        if action_id == "scs.throttle":
            fraction = max(0.0, min(1.0, float(params.get("throttle", 0.5))))
            if self._mode == "vgamepad" and self._pad is not None:
                self._pad.right_trigger_float(value_float=fraction)
                self._pad.update()
                return True, None
            return self._keyboard_axis(VK_W, fraction, label="throttle")
        return False, f"unknown scs action {action_id!r}"

    def reset(self) -> None:
        """Release held virtual-pad triggers (kill-switch / session end)."""
        if self._pad is None or self._mode != "vgamepad":
            return
        try:
            self._pad.left_trigger_float(value_float=0.0)
            self._pad.right_trigger_float(value_float=0.0)
            self._pad.update()
        except Exception as exc:
            log.warning("scs_pad_reset_failed", err=str(exc))

    def _keyboard_axis(self, vk: int, fraction: float, *, label: str) -> tuple[bool, str | None]:
        hold_s = max(0.05, min(1.5, fraction))
        try:
            self._key_hold(vk, hold_s=hold_s)
            return True, None
        except Exception as exc:
            return False, f"keyboard {label} failed: {exc}"

    def _key_hold(self, vk: int, *, hold_s: float) -> None:
        if self._key_hold_fn is not None:
            self._key_hold_fn(vk, hold_s=hold_s)
            return
        from titan_actions.win_input import key_hold

        key_hold(vk, hold_s=hold_s)
