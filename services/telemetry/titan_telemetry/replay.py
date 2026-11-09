"""Replay fixture frames at 1x, 2x, or 10x (Section 7.1)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal
from uuid import UUID

from titan_core.logging import get_logger
from titan_sdk_games.adapter import GameAdapter
from titan_telemetry.pipeline import iter_fixture, run_fixture

log = get_logger(__name__)

ReplaySpeed = Literal[1, 2, 10]


async def replay_sleep(delta_s: float, speed: ReplaySpeed) -> None:
    await asyncio.sleep(delta_s / float(speed))


async def drain_fixture(
    adapter: GameAdapter,
    rules_path: Path,
    fixture_path: Path,
    *,
    session_id: UUID,
    game: str,
    adapter_version: str,
    speed: ReplaySpeed = 1,
) -> None:
    """Yield frames with timing for integration tests."""
    prev_ms: int | None = None
    for raw in iter_fixture(fixture_path):
        t_ms = int(raw.get("t_session_ms", 0))
        if prev_ms is not None and t_ms > prev_ms:
            await replay_sleep((t_ms - prev_ms) / 1000.0, speed)
        prev_ms = t_ms
    result = run_fixture(
        adapter, rules_path, fixture_path, session_id=session_id, game=game, adapter_version=adapter_version
    )
    log.info(
        "replay_complete",
        frames=result.frames,
        events=len(result.events),
        speed=speed,
        fixture=str(fixture_path),
    )
