"""Child process spawning and tree termination (Sections 2.3 and 2.7)."""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import os
import signal
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any

import psutil

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
CREATE_NO_WINDOW = 0x08000000
_PR_SET_PDEATHSIG = 1


def _die_with_parent() -> None:  # pragma: no cover - runs in the forked child
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)


def sweep_descendants() -> int:
    """Kill every process still descending from this one. Returns how many there were."""
    leftovers = descendants(os.getpid())
    kill_all(leftovers)
    return len(leftovers)


def spawn_kwargs(platform: str = sys.platform) -> dict[str, Any]:
    """Titan's Python processes run below normal priority on Windows (Section 2.7) with no console
    window; the supervisor's job object (`winjob`) ties their lifetime to it. On Linux each child
    gets SIGKILL if the supervisor dies."""
    if platform == "win32":
        return {"creationflags": CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS}
    if platform.startswith("linux"):
        return {"preexec_fn": _die_with_parent}
    return {"start_new_session": False}


async def spawn(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    stdout: IO[bytes] | int = asyncio.subprocess.PIPE,
) -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=stdout,
        stderr=asyncio.subprocess.STDOUT,
        env=dict(env) if env is not None else None,
        cwd=cwd,
        **spawn_kwargs(),
    )
    return proc


async def wait_exit(proc: asyncio.subprocess.Process, timeout_s: float | None = None) -> bool:
    """Wait until the process has exited; True if it did within `timeout_s`.

    Unlike `Process.wait()`, this does not also wait for its stdout pipe to close, which a
    surviving grandchild can keep open indefinitely.
    """
    loop = asyncio.get_running_loop()
    deadline = None if timeout_s is None else loop.time() + timeout_s
    while proc.returncode is None:
        if deadline is not None and loop.time() >= deadline:
            return False
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(proc.wait()), 0.2)
    return True


def descendants(pid: int) -> list[psutil.Process]:
    try:
        return psutil.Process(pid).children(recursive=True)
    except psutil.Error:
        return []


async def terminate_tree(proc: asyncio.subprocess.Process, timeout_s: float = 5.0) -> None:
    """Ask the process to exit, kill it after `timeout_s`, then kill anything it left behind.

    On Windows `terminate()` is TerminateProcess, so children get no chance to clean up; Titan's
    children keep no state that needs it (Postgres is stopped with `pg_ctl`, not through here).
    """
    children = descendants(proc.pid)
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        if not await wait_exit(proc, timeout_s):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await wait_exit(proc)
    kill_all(children)


def kill_all(processes: Sequence[psutil.Process], timeout_s: float = 3.0) -> None:
    alive = []
    for process in processes:
        with contextlib.suppress(psutil.Error):
            process.terminate()
            alive.append(process)
    _, still = psutil.wait_procs(alive, timeout=timeout_s)
    for process in still:
        with contextlib.suppress(psutil.Error):
            process.kill()


def kill_tree_by_pid(pid: int | None) -> None:
    if pid is None:
        return
    try:
        root = psutil.Process(pid)
    except psutil.Error:
        return
    kill_all([*descendants(pid), root])


def pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False
