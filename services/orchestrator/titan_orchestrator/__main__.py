"""`python -m titan_orchestrator --session-id ...` entry point."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from uuid import UUID

from titan_core.ids import uuid7
from titan_core.logging import configure_logging, get_logger
from titan_orchestrator.runtime import SessionRuntime
from titan_orchestrator.session_loops import run_session_loops
from titan_orchestrator.teams import load_team_template, template_to_roster

log = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="titan-orchestrator")
    parser.add_argument("--session-id", required=True, type=UUID)
    parser.add_argument("--game-slug", default="ksp")
    return parser.parse_args(argv)


async def _run(session_id: UUID, game_slug: str) -> int:
    runtime = await SessionRuntime.create(session_id)
    template = load_team_template(game_slug)
    roster = []
    for agent in template_to_roster(template):
        roster.append({**agent, "instance_id": uuid7()})
    await runtime.register_team(roster)
    await runtime.start()
    play_enabled = os.environ.get("TITAN_SESSION_PLAY") == "1"
    loops = asyncio.create_task(
        run_session_loops(runtime, play_enabled=play_enabled),
        name="session-loops",
    )
    log.info("orchestrator_started", session_id=str(session_id), game=game_slug)
    stop = asyncio.Event()
    try:
        await stop.wait()
    except asyncio.CancelledError:
        pass
    finally:
        loops.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await loops
        await runtime.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging("orchestrator")
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args.session_id, args.game_slug))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
