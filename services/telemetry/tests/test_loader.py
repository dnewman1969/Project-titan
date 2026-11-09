from __future__ import annotations

from titan_telemetry.loader import adapter_for, rules_path
from titan_game_ksp.adapter import KspAdapter


def test_load_ksp_adapter() -> None:
    cls = adapter_for("ksp")
    assert cls is KspAdapter
    assert rules_path(cls).name == "events.yaml"
