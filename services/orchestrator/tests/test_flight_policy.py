"""KSP flight setpoints — fly the vessel, not a one-shot poke."""

from __future__ import annotations

import pytest

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
    assert decision.status == "climb"


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


def test_early_slow_craft_holds_a_shallow_climb() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 400.0},
                "velocity": {"speed_mps": 12.0, "vertical_mps": 10.0, "horizontal_mps": 4.0},
            }
        )
    )
    assert decision.status == "climb"
    assert decision.proposal is not None
    assert decision.proposal["params"]["pitch_deg"] == 60.0
    assert decision.proposal["params"]["heading_deg"] == 90.0
    assert decision.stage_once is False


def test_early_climb_follows_surface_prograde() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 2_000.0},
                "velocity": {"speed_mps": 180.0, "vertical_mps": 70.0, "horizontal_mps": 160.0},
                "prograde_pitch_deg": 23.0,
                "prograde_heading_deg": 88.0,
            }
        )
    )
    assert decision.status == "prograde"
    assert decision.proposal is not None
    assert decision.proposal["params"]["pitch_deg"] == 25.0
    assert decision.proposal["params"]["heading_deg"] == 90.0
    assert decision.proposal["params"]["sas"] is False


def test_aligned_heading_releases_the_autopilot_to_sas() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 22_625.0},
                "velocity": {"speed_mps": 400.0, "vertical_mps": 80.0, "horizontal_mps": 390.0},
                "attitude": {"heading_deg": 90.0, "pitch_deg": 45.0, "roll_deg": 2.0},
            }
        )
    )
    assert decision.status == "heading"
    assert decision.proposal is not None
    params = decision.proposal["params"]
    assert params["sas"] is True
    assert params["sas_mode"] == "stability"
    assert "pitch_deg" not in params
    assert "SAS on" in decision.message


def test_tumble_cuts_throttle_and_damps_before_steering() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 4_000.0},
                "velocity": {"speed_mps": 200.0, "vertical_mps": 80.0, "horizontal_mps": 150.0},
                "attitude": {"heading_deg": 40.0, "pitch_deg": 80.0, "roll_deg": 70.0},
                "angular_rate_rad_s": 0.9,
                "controls": {"throttle": 1.0},
            }
        )
    )
    assert decision.status == "damp"
    assert decision.stage_once is False
    assert decision.proposal is not None
    params = decision.proposal["params"]
    assert params["throttle"] == 0.0
    assert params["sas"] is True
    assert "pitch_deg" not in params
    assert "heading_deg" not in params
    assert "damping" in decision.message


def test_overheat_cuts_throttle() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 6_000.0},
                "velocity": {"speed_mps": 200.0, "vertical_mps": 80.0, "horizontal_mps": 160.0},
                "engine": {"max_temp_ratio": 0.91},
                "controls": {"throttle": 0.8},
            }
        )
    )
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.0
    assert "Overheating" in decision.message
    assert "80%" in decision.message


def test_thick_air_speed_cuts_throttle() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 8_000.0},
                "velocity": {"speed_mps": 340.0, "vertical_mps": 40.0, "horizontal_mps": 330.0},
            }
        )
    )
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.0
    assert "sensible speed" in decision.message
    assert decision.stage_once is False


def test_fast_above_thick_air_keeps_throttle() -> None:
    decision = decide_flight(
        _frame(
            vehicle={
                "geo": {"alt_m": 20_000.0},
                "velocity": {"speed_mps": 900.0, "vertical_mps": 100.0, "horizontal_mps": 880.0},
            }
        )
    )
    assert decision.status == "heading"
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 1.0


def test_policy_reads_a_fake_vessel() -> None:
    """Sampler → normalized frame → decision. No live kRPC."""
    from titan_game_ksp import vessel_sample
    from titan_game_ksp.adapter import KspAdapter
    from titan_game_ksp.vessel_sample import sample_vessel

    vessel_sample._HEAT_CACHE = None

    class _Flight:
        mean_altitude = 4500.0
        latitude = 0.0
        longitude = 0.0
        speed = 220.0
        vertical_speed = 90.0
        horizontal_speed = 180.0
        g_force = 2.0
        dynamic_pressure = 1000.0
        static_pressure = 10000.0
        atmosphere_density = 0.4
        heading = 20.0
        pitch = 70.0
        roll = 55.0

    class _Part:
        temperature = 1800.0
        max_temperature = 2000.0
        skin_temperature = 900.0
        max_skin_temperature = 2000.0

    class _Parts:
        all = (_Part(),)

    class _Control:
        throttle = 1.0
        sas = False
        rcs = False
        current_stage = 1

    class _Situation:
        name = "flying"

    class _Vessel:
        name = "Explorer"
        situation = _Situation()
        surface_reference_frame = "srf"
        control = _Control()
        orbit = None
        parts = _Parts()

        def flight(self, ref: object = None) -> _Flight:
            assert ref == "srf"
            return _Flight()

        def angular_velocity(self, ref: object = None) -> tuple[float, float, float]:
            assert ref == "srf"
            return (0.6, 0.0, 0.8)

        def velocity(self, ref: object = None) -> tuple[float, float, float]:
            assert ref == "srf"
            return (90.0, 0.0, 180.0)

    class _Scene:
        name = "flight"

    class _Krpc:
        current_game_scene = _Scene()
        paused = False

    class _Center:
        active_vessel = _Vessel()

    class _Conn:
        space_center = _Center()
        krpc = _Krpc()

    raw = sample_vessel(_Conn())
    assert raw["angular_rate_rad_s"] == pytest.approx(1.0)
    assert raw["max_temp_ratio"] == pytest.approx(0.9)
    frame = KspAdapter().normalize(raw).model_dump(mode="json")
    decision = decide_flight(frame)
    assert decision.status == "damp"
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.0
    assert decision.proposal["params"]["sas"] is True
    assert "pitch_deg" not in decision.proposal["params"]
    assert "Tumbling" in decision.message


def test_crew_agents_may_write_learn_sections() -> None:
    assert "agent" in SECTION_WRITERS["lessons"]
    assert "agent" in SECTION_WRITERS["notes"]
    assert "agent" in SECTION_WRITERS["discoveries"]
