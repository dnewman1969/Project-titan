"""Start/stop per-session telemetry children (fixture replay or live adapter)."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path
from uuid import UUID

from titan_api.demo_replay import ksp_fixture_path, stop_demo_replay
from titan_core.logging import get_logger

log = get_logger(__name__)

_LIVE_PROCS: dict[UUID, asyncio.subprocess.Process] = {}
_LIVE_WATCH: dict[UUID, asyncio.Task[None]] = {}


async def start_live_telemetry(
    session_id: UUID,
    *,
    game_slug: str,
    install_path: str,
) -> None:
    if session_id in _LIVE_PROCS and _LIVE_PROCS[session_id].returncode is None:
        return
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "titan_telemetry",
        "--game",
        game_slug,
        "--session-id",
        str(session_id),
        "--install-path",
        install_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _LIVE_PROCS[session_id] = proc
    log.info(
        "live_telemetry_started",
        session_id=str(session_id),
        game=game_slug,
        install_path=install_path,
        pid=proc.pid,
    )

    async def _watch() -> None:
        try:
            _ = await proc.wait()
        finally:
            _LIVE_PROCS.pop(session_id, None)
            _LIVE_WATCH.pop(session_id, None)
            if proc.returncode not in (0, None):
                err = (await proc.stderr.read()).decode() if proc.stderr else ""
                log.warning(
                    "live_telemetry_exited",
                    session_id=str(session_id),
                    code=proc.returncode,
                    err=err[:500],
                )

    _LIVE_WATCH[session_id] = asyncio.create_task(_watch(), name=f"live-telemetry-{session_id}")


def stop_live_telemetry(session_id: UUID) -> None:
    proc = _LIVE_PROCS.pop(session_id, None)
    if proc is None or proc.returncode is not None:
        return
    proc.terminate()
    with contextlib.suppress(ProcessLookupError):
        log.info("live_telemetry_stopped", session_id=str(session_id))


def stop_all_session_telemetry(session_id: UUID) -> None:
    stop_demo_replay(session_id)
    stop_live_telemetry(session_id)


def fixture_fallback_path(game_slug: str) -> Path | None:
    if game_slug == "ksp":
        path = ksp_fixture_path()
        return path if path.is_file() else None
    return None
