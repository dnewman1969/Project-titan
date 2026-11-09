"""How Titan starts a discovered game executable.

KSP is a Unity player. Its flip-model swap chain is valid only on a top-level window, so the
desktop docks that window into the Operations Center instead of reparenting it. Starting
borderless (no exclusive fullscreen) is what makes the dock stick.
"""

from __future__ import annotations

_UNITY_PLAYERS = {"ksp_x64.exe", "ksp.exe"}


def _exe_name(executable: str) -> str:
    """Last path segment, whether the string uses Windows or POSIX separators."""
    return executable.replace("\\", "/").rsplit("/", 1)[-1].lower()


def game_process_argv(executable: str) -> list[str]:
    """Argv for a direct executable launch. Does not use a shell."""
    argv = [executable]
    if _exe_name(executable) in _UNITY_PLAYERS:
        argv.extend(["-screen-fullscreen", "0", "-popupwindow"])
    return argv
