from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from titan_game_ats.adapter import AtsAdapter
from titan_game_ets2.adapter import Ets2Adapter
from titan_game_ksp.adapter import KspAdapter

from titan_telemetry.loader import rules_path
from titan_telemetry.pipeline import canonical_events_ndjson, run_fixture

SESSION = UUID(int=0)
ROOT = Path(__file__).resolve().parents[2]

CASES = [
    (
        "ksp",
        KspAdapter,
        "games/ksp/fixtures/launch-to-orbit.ndjson",
        "games/ksp/fixtures/golden/launch-to-orbit.events.ndjson",
    ),
    ("ksp", KspAdapter, "games/ksp/fixtures/crash.ndjson", "games/ksp/fixtures/golden/crash.events.ndjson"),
    (
        "ets2",
        Ets2Adapter,
        "games/ets2/fixtures/delivery-fine.ndjson",
        "games/ets2/fixtures/golden/delivery-fine.events.ndjson",
    ),
    (
        "ats",
        AtsAdapter,
        "games/ats/fixtures/short-haul-low-fuel.ndjson",
        "games/ats/fixtures/golden/short-haul-low-fuel.events.ndjson",
    ),
]


@pytest.mark.parametrize(("slug", "adapter_cls", "fixture", "golden"), CASES)
def test_fixture_replay_matches_golden(
    slug: str,
    adapter_cls: type,
    fixture: str,
    golden: str,
) -> None:
    adapter = adapter_cls()
    manifest = adapter_cls.load_manifest()
    result = run_fixture(
        adapter,
        rules_path(adapter_cls),
        ROOT / fixture,
        session_id=SESSION,
        game=slug,
        adapter_version=manifest.adapter_version,
    )
    expected = (ROOT / golden).read_text(encoding="utf-8")
    assert canonical_events_ndjson(result.events) == expected
