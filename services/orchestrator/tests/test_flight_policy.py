"""KSP flight setpoints — heading hold, not a one-shot poke."""

from __future__ import annotations

from titan_orchestrator.blackboard import SECTION_WRITERS
from titan_orchestrator.flight_policy import command_signature, decide_flight


def _frame(**overrides: object) -> dict[str, object]:
    vehicle: dict[str, object] = {
        "name": "Explorer",
        "situation": "flying",
        "geo": {"lat_deg": 0.0, "lon_deg": 0.0, "alt_m": 1000.0},
        "velocity": {"speed_mps": 50.0, "vertical_mps": 40.0, "horizontal_mps": 10.0},
    }
    frame: dict[str, object] = {
        "scene": "flight",
        "paused": False,
        "vehicle": vehicle,
        "environment": {"dynamic_pressure_pa": 0.0},
    }
    vehicle_over = overrides.pop("vehicle", None)
    if isinstance(vehicle_over, dict):
        vehicle.update(vehicle_over)
    frame.update(overrides)
    return frame


def test_no_flight_scene_does_not_steer() -> None:
    decision = decide_flight({"scene": "space_center", "paused": False, "vehicle": None})
    assert decision.proposal is None
    assert decision.status == "no_vessel"
    assert "not steering" in decision.message
    assert "space_center" in decision.message


def test_unnamed_flight_scene_does_not_steer() -> None:
    decision = decide_flight(
        {"scene": "flight", "paused": False, "vehicle": {"name": None, "situation": "pre_launch"}}
    )
    assert decision.proposal is None
    assert "no active vessel" in decision.message


def test_paused_does_not_steer() -> None:
    decision = decide_flight(_frame(paused=True))
    assert decision.proposal is None
    assert decision.status == "paused"


def test_launch_holds_vertical_east_and_stages_once() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "situation": "pre_launch",
                "geo": {"lat_deg": 0.0, "lon_deg": 0.0, "alt_m": 70.0},
                "velocity": {"vertical_mps": 0.0},
            }
        )
    )
    assert decision.stage_once is True
    assert decision.proposal is not None
    params = decision.proposal["params"]
    assert params["throttle"] == 1.0
    assert params["pitch_deg"] == 90.0
    assert params["heading_deg"] == 90.0
    assert params["sas"] is False


def test_ascent_pitches_down_with_altitude() -> None:
    low = decide_flight(_frame(vehicle={"geo": {"alt_m": 1000.0}}))
    mid = decide_flight(_frame(vehicle={"geo": {"alt_m": 22625.0}}))
    assert low.proposal is not None and mid.proposal is not None
    assert low.proposal["params"]["pitch_deg"] > mid.proposal["params"]["pitch_deg"]
    assert mid.proposal["params"]["pitch_deg"] == 45.0
    assert mid.proposal["params"]["heading_deg"] == 90.0
    assert mid.proposal["params"]["throttle"] == 1.0


def test_max_q_eases_throttle() -> None:
    decision = decide_flight(
        _frame(
            environment={"dynamic_pressure_pa": 30_000.0},
            vehicle={"geo": {"alt_m": 5000.0}, "velocity": {"vertical_mps": 200.0}},
        )
    )
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.65
    assert decision.status == "ascent"


def test_low_descent_pitches_up() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "situation": "flying",
                "geo": {"alt_m": 100.0},
                "velocity": {"vertical_mps": -40.0},
            }
        )
    )
    assert decision.status == "recover"
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 1.0
    assert decision.proposal["params"]["pitch_deg"] == 75.0


def test_high_apoapsis_coasts() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "situation": "flying",
                "geo": {"alt_m": 40_000.0},
                "velocity": {"vertical_mps": 20.0},
                "orbit": {"apoapsis_m": 90_000.0},
            }
        )
    )
    assert decision.status == "coast"
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.0
    assert "heading_deg" in decision.proposal["params"]


def test_orbit_releases_heading_hold() -> None:
    decision = decide_flight(_frame(vehicle={"situation": "orbiting"}))
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.0
    assert decision.proposal["params"]["sas"] is True
    assert "pitch_deg" not in decision.proposal["params"]


def test_signature_changes_when_staging() -> None:
    decision = decide_flight(_frame(vehicle={"situation": "pre_launch", "geo": {"alt_m": 0.0}}))
    assert command_signature(decision, staging=False) != command_signature(decision, staging=True)


def test_crew_agents_may_write_learn_sections() -> None:
    assert "agent" in SECTION_WRITERS["lessons"]
    assert "agent" in SECTION_WRITERS["notes"]
    assert "agent" in SECTION_WRITERS["discoveries"]
