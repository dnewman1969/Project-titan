"""SCS event rules that feed learn→play (speeding / collision)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from titan_core.protocol.telemetry import (
    TELEMETRY_SCHEMA,
    Damage,
    Environment,
    TelemetryFrame,
    Vehicle,
    Velocity,
)
from titan_telemetry.rules import RuleEngine

SESSION = UUID(int=7)
RULES = Path(__file__).resolve().parents[3] / "games/ets2/events.yaml"


def _frame(*, speed: float, damage: float | None = None, t_ms: int = 1000) -> TelemetryFrame:
    return TelemetryFrame.model_validate(
        {
            "schema": TELEMETRY_SCHEMA,
            "session_id": SESSION,
            "game": "ets2",
            "adapter_version": "1.0.0",
            "seq": 1,
            "t_mono_ns": t_ms * 1_000_000,
            "t_session_ms": t_ms,
            "t_game_s": 0.0,
            "paused": False,
            "scene": "driving",
            "domain": "ground_vehicle",
            "vehicle": Vehicle(
                name=None,
                kind="truck",
                position=None,
                geo=None,
                attitude=None,
                velocity=Velocity(speed_mps=speed, vertical_mps=None, horizontal_mps=None),
                accel_g=None,
                controls=None,
                engine=None,
                damage=Damage(overall=damage, parts={}),
                situation=None,
                stage=None,
                orbit=None,
            ),
            "resources": [],
            "environment": Environment(
                body=None,
                atmosphere_density=None,
                dynamic_pressure_pa=None,
                static_pressure_pa=None,
                speed_limit_mps=25.0,
                weather=None,
                local_time=None,
            ),
            "job": None,
            "economy": None,
            "game_specific": {},
        }
    )


def test_vehicle_speeding_rule_fires() -> None:
    engine = RuleEngine.from_yaml(RULES, session_id=SESSION, game="ets2")
    assert not engine.evaluate(_frame(speed=24, t_ms=0), t_session_ms=0, paused=False)
    fired = engine.evaluate(_frame(speed=30, t_ms=500), t_session_ms=500, paused=False)
    assert any(ev.type == "vehicle.speeding" for ev in fired)


def test_vehicle_collision_rule_on_damage_jump() -> None:
    engine = RuleEngine.from_yaml(RULES, session_id=SESSION, game="ets2")
    assert not engine.evaluate(_frame(speed=20, damage=0.0, t_ms=0), t_session_ms=0, paused=False)
    fired = engine.evaluate(_frame(speed=18, damage=0.08, t_ms=400), t_session_ms=400, paused=False)
    assert any(ev.type == "vehicle.collision" for ev in fired)
