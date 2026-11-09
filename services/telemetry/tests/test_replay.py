from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from titan_game_ksp.adapter import KspAdapter
from titan_telemetry.loader import rules_path
from titan_telemetry.replay import drain_fixture

ROOT = Path(__file__).resolve().parents[3]


def test_drain_fixture_completes() -> None:
    asyncio.run(
        drain_fixture(
            KspAdapter(),
            rules_path(KspAdapter),
            ROOT / "games/ksp/fixtures/crash.ndjson",
            session_id=UUID(int=0),
            game="ksp",
            adapter_version="1.0.0",
            speed=10,
        )
    )
