from __future__ import annotations

from pathlib import Path

from titan_sdk_games.parsers.ksp_settings import parse_ksp_settings_cfg
from titan_sdk_games.parsers.scs_sii import parse_scs_controls_sii

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_ksp_settings_cfg() -> None:
    bindings = parse_ksp_settings_cfg(FIXTURES / "ksp_settings.cfg")
    keys = {b.action_id: b.binding["key"] for b in bindings}
    assert keys["ksp.stage"] == "Space"
    assert keys["ksp.throttle"] == "LeftShift"
    assert bindings[0].source == "config_file"


def test_parse_scs_controls_sii() -> None:
    bindings = parse_scs_controls_sii(FIXTURES / "controls.sii")
    action_ids = {b.action_id for b in bindings}
    assert "scs.shift_up" in action_ids
    assert "scs.cruise_control" in action_ids


def test_parse_scs_ignores_unknown_actions() -> None:
    assert parse_scs_controls_sii(FIXTURES / "controls_minimal.sii") == []
