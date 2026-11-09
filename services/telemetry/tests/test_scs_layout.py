from __future__ import annotations

from pathlib import Path

import pytest
from titan_game_scs.layout import ScsLayout
from titan_game_scs.shm import encode_test_blob


def test_scs_layout_roundtrip() -> None:
    layout = ScsLayout.from_yaml(
        Path(__file__).resolve().parents[3] / "games/scs-common/titan_game_scs/layouts/rencloud-1.12.yaml"
    )
    blob = encode_test_blob(
        layout,
        {
            "sdk_active": True,
            "paused": False,
            "plugin_revision": 12,
            "game_id": 1,
            "timestamp": 99,
            "speed_mps": 25.5,
            "fuel_l": 120.0,
            "fuel_capacity_l": 400.0,
            "gear": 8,
            "game_time_min": 42,
            "job_active": True,
            "job_delivered": False,
            "player_fined": False,
            "nav_distance_m": 12000.0,
            "speed_limit_mps": 22.0,
            "cargo_damage": 0.0,
        },
    )
    parsed = layout.read(blob)
    assert parsed["speed_mps"] == pytest.approx(25.5)
    assert parsed["fuel_l"] == pytest.approx(120.0)
