from __future__ import annotations

from pathlib import Path
from uuid import UUID

from titan_core.protocol.telemetry import (
    TELEMETRY_SCHEMA,
    Damage,
    Resource,
    TelemetryFrame,
    Vehicle,
    Velocity,
)
from titan_telemetry.rules import RuleEngine

SESSION = UUID(int=0)


def _frame(**kwargs: object) -> TelemetryFrame:
    base = dict(
        schema=TELEMETRY_SCHEMA,
        session_id=SESSION,
        game="ets2",
        adapter_version="1.0.0",
        seq=1,
        t_mono_ns=1,
        t_session_ms=1000,
        t_game_s=0.0,
        paused=False,
        scene="driving",
        domain="ground_vehicle",
        vehicle=Vehicle(
            name=None,
            kind="truck",
            position=None,
            geo=None,
            attitude=None,
            velocity=Velocity(speed_mps=10, vertical_mps=None, horizontal_mps=None),
            accel_g=None,
            controls=None,
            engine=None,
            damage=Damage(overall=None, parts={}),
            situation=None,
            stage=None,
            orbit=None,
        ),
        resources=[Resource(id="fuel", name="Diesel", amount=30, capacity=400, unit="L", scope="vehicle")],
        environment=None,
        job=None,
        economy=None,
        game_specific={},
    )
    base.update(kwargs)
    return TelemetryFrame.model_validate(base)


def test_fuel_low_rule_fires_after_for_s(tmp_path: Path) -> None:
    rules = tmp_path / "events.yaml"
    rules.write_text(
        """
- id: vehicle.fuel_low
  type: vehicle.fuel_low
  when:
    all:
      - { path: "resources[id=fuel].ratio", op: "<", value: 0.15 }
      - { path: "paused", op: "==", value: false }
  for_s: 2
  severity: warning
  salience: 0.6
""".strip(),
        encoding="utf-8",
    )
    engine = RuleEngine.from_yaml(rules, session_id=SESSION, game="ets2")
    assert not engine.evaluate(_frame(t_session_ms=0), t_session_ms=0, paused=False)
    assert not engine.evaluate(_frame(t_session_ms=1000), t_session_ms=1000, paused=False)
    fired = engine.evaluate(_frame(t_session_ms=2500), t_session_ms=2500, paused=False)
    assert fired and fired[0].type == "vehicle.fuel_low"
