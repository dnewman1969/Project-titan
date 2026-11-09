"""Low-level keyboard input (Windows only)."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        _anonymous_ = ("ii",)
        _fields_ = [("type", wintypes.DWORD), ("ii", _I)]

    def _send_vk(vk: int, *, key_up: bool) -> None:
        flags = KEYEVENTF_KEYUP if key_up else 0
        extra = ctypes.c_ulong(0)
        inp = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=ctypes.pointer(extra)),
        )
        if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
            raise OSError("SendInput failed")

    def key_hold(vk: int, *, hold_s: float) -> None:
        _send_vk(vk, key_up=False)
        time.sleep(hold_s)
        _send_vk(vk, key_up=True)
else:

    def key_hold(vk: int, *, hold_s: float) -> None:
        raise OSError("SendInput is only available on Windows")
