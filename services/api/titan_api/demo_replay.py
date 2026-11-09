"""Spawn KSP fixture replay into Redis session streams (no game install required)."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path
from uuid import UUID

from titan_core.config import find_app_config_dir
from titan_core.logging import get_logger

log = get_logger(__name__)

_DEMO_PROCS: dict[UUID, asyncio.subprocess.Process] = {}
_DEMO_WATCH: dict[UUID, asyncio.Task[None]] = {}


def ksp_fixture_path() -> Path:
    root = find_app_config_dir().parent
    return root / "games" / "ksp" / "fixtures" / "launch-to-orbit.ndjson"


async def start_demo_replay(session_id: UUID, *, speed: int = 2) -> None:
    """Replay the launch fixture on loop for Phase 1 desktop demo."""
    if session_id in _DEMO_PROCS and _DEMO_PROCS[session_id].returncode is None:
        return
    fixture = ksp_fixture_path()
    if not fixture.is_file():
        log.warning("demo_fixture_missing", path=str(fixture))
        return
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "titan_telemetry",
        "--game",
        "ksp",
        "--replay",
        str(fixture),
        "--session-id",
        str(session_id),
        "--speed",
        str(speed),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _DEMO_PROCS[session_id] = proc
    log.info("demo_replay_started", session_id=str(session_id), pid=proc.pid, speed=speed)

    async def _watch() -> None:
        try:
            _ = await proc.wait()
        finally:
            _DEMO_PROCS.pop(session_id, None)
            _DEMO_WATCH.pop(session_id, None)
            if proc.returncode not in (0, None):
                err = (await proc.stderr.read()).decode() if proc.stderr else ""
                log.warning(
                    "demo_replay_exited",
                    session_id=str(session_id),
                    code=proc.returncode,
                    err=err[:500],
                )

    _DEMO_WATCH[session_id] = asyncio.create_task(_watch(), name=f"demo-replay-{session_id}")


def stop_demo_replay(session_id: UUID) -> None:
    proc = _DEMO_PROCS.pop(session_id, None)
    if proc is None or proc.returncode is not None:
        return
    proc.terminate()
    with contextlib.suppress(ProcessLookupError):
        log.info("demo_replay_stopped", session_id=str(session_id))


async def stop_all_demo_replays() -> None:
    for sid in list(_DEMO_PROCS):
        stop_demo_replay(sid)
