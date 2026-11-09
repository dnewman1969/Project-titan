"""Continuous KSP setpoints: fly the vessel, not a one-shot heading poke.

kRPC's autopilot holds a pitch and heading until the next call
(``target_pitch_and_heading`` in the surface frame — the launch-into-orbit
tutorial). It will not run at the same time as SAS. kOS does the same split:
``lock steering to srfprograde`` (or ``heading()``) while the direction is
still changing, then ``SAS on`` once the nose is already there. A short
``stopping_time`` hunts and tumbles a tall rocket, so the driver eases the
autopilot; this policy stops retargeting once the vessel is aligned.

While flying, the early phase follows surface prograde when that direction is
a climb, and a shallow pitch on heading 90° east when prograde is still noise.
After that it holds one heading. Throttle goes to zero if a part is
overheating or the craft is too fast in thick air. A high angular rate cuts
throttle and asks SAS to damp rotation before any new steering. Staging is
only the single pre-launch light-the-engine pulse.

MechJeb and kOS are not required. The inputs are the telemetry frame the kRPC
sampler already publishes (situation, altitude, speed, throttle, attitude,
angular rate, prograde, part temperature).

A career ``FlightGoal`` replaces that generic climb. The setpoint then follows
the contract step (altitude, orbit, part test, or recovery) instead of
coasting at 80 km because the vessel left the pad.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from titan_orchestrator.career import FlightGoal

LAUNCH_HEADING_DEG = 90.0
TURN_START_M = 250.0
TURN_END_M = 45_000.0
EARLY_ALT_M = 10_000.0
SHALLOW_CLIMB_PITCH_DEG = 60.0
APOAPSIS_COAST_M = 80_000.0
COAST_ALT_M = 30_000.0
RECOVER_ALT_M = 800.0
RECOVER_VS_MPS = -15.0
MAX_Q_PA = 25_000.0
MAX_Q_THROTTLE = 0.65
# ~20 deg/s. A gravity turn is a few degrees per second; this is a tumble.
TUMBLE_RATE_RAD_S = 0.35
OVERHEAT_RATIO = 0.85
# Thick air. Faster than this low down cooks fairings and fins.
THICK_AIR_ALT_M = 12_000.0
SENSIBLE_SPEED_MPS = 280.0
PROGRADE_MIN_MPS = 30.0
PROGRADE_MIN_PITCH_DEG = 8.0
HEADING_TOL_DEG = 12.0
PITCH_TOL_DEG = 8.0
ROLL_TOL_DEG = 20.0

_EFFECT_HOLD = "Autopilot holds pitch and heading; throttle follows the ascent."
_EFFECT_SAS = "SAS holds the current attitude; autopilot released."


def decide_flight(frame: Mapping[str, Any], *, goal: FlightGoal | None = None) -> FlightDecision:
    """Choose the next KSP setpoint from a telemetry frame dict.

    When ``goal`` is set, the setpoint follows that contract step. The generic
    ascent is only used when no contract is in play.
    """
    if goal is not None:
        return _decide_goal(frame, goal)
    scene = str(frame.get("scene") or "").strip()
    if scene != "flight":
        shown = scene or "unknown"
        return FlightDecision(
            status="no_vessel",
            message=(f"No active flight scene (scene={shown}). Load a vessel and launch — not steering."),
        )
    if bool(frame.get("paused")):
        return FlightDecision(status="paused", message="Flight is paused — not sending controls.")

    vehicle = frame.get("vehicle")
    if not isinstance(vehicle, dict):
        return FlightDecision(
            status="no_vessel",
            message="No active vessel in the flight scene — not steering.",
        )
    name = vehicle.get("name")
    named = isinstance(name, str) and bool(name.strip())
    alt = _alt(vehicle)
    situation = _situation(vehicle)
    if not named and alt is None:
        return FlightDecision(
            status="no_vessel",
            message="Flight scene has no active vessel — not steering.",
        )

    vspeed = _vspeed(vehicle)
    apo = _apoapsis(vehicle)
    dyn = _dynamic_pressure(frame)
    alt_m = 0.0 if alt is None else alt
    speed = _speed(vehicle)
    ang = _angular_rate(vehicle)
    heading = _axis(vehicle, "heading_deg")
    pitch = _axis(vehicle, "pitch_deg")
    roll = _axis(vehicle, "roll_deg")
    temp = _temp_ratio(vehicle)
    throttle_now = _throttle(vehicle)
    prograde_pitch, prograde_heading = _prograde(vehicle)

    if situation in {"landed", "splashed"}:
        return FlightDecision(
            status="landed",
            message="Vessel is on the ground — throttle idle, SAS on. Not steering a heading.",
            proposal=_sas_only(0.0, "Vessel is on the ground — throttle idle, SAS on."),
            situation=situation,
        )
    if situation in {"orbiting", "escaping", "docked"}:
        return FlightDecision(
            status="orbit",
            message="Coasting in orbit — throttle idle, SAS on. Not forcing a new heading.",
            proposal=_sas_only(0.0, "In orbit — throttle idle and SAS on."),
            situation=situation,
        )

    if situation == "pre_launch" or (situation is None and alt_m < TURN_START_M and (vspeed or 0) <= 0):
        message = (
            "Launch hold: throttle full, autopilot pitch 90° heading 90° east. "
            "Staging once to light the engine."
        )
        return FlightDecision(
            status="launch",
            message=message,
            proposal=_guided(1.0, 90.0, LAUNCH_HEADING_DEG, message, _EFFECT_HOLD),
            stage_once=True,
            situation=situation or "pre_launch",
        )

    if ang is not None and ang >= TUMBLE_RATE_RAD_S:
        roll_bit = f", roll {roll:.0f}°" if roll is not None else ""
        message = (
            f"Tumbling at {ang:.2f} rad/s{roll_bit} — throttle idle and SAS damping rotation "
            "before steering again."
        )
        return FlightDecision(
            status="damp",
            message=message,
            proposal=_sas_only(0.0, message),
            situation=situation,
        )

    overheating = temp is not None and temp >= OVERHEAT_RATIO
    too_fast = (
        speed is not None and alt_m < THICK_AIR_ALT_M and speed >= SENSIBLE_SPEED_MPS and not overheating
    )

    recovering = (
        situation not in {"pre_launch", "landed", "splashed"}
        and alt_m < RECOVER_ALT_M
        and vspeed is not None
        and vspeed < RECOVER_VS_MPS
    )
    if recovering:
        throttle = 0.0 if overheating else 1.0
        if overheating:
            message = (
                "Low and descending, but a part is overheating — throttle cut, "
                f"pitch 75° on heading {LAUNCH_HEADING_DEG:.0f}°."
            )
        else:
            message = (
                "Low and descending — full throttle and pitch 75° on heading 90° "
                "so the vessel does not hit the ground."
            )
        return FlightDecision(
            status="recover",
            message=message,
            proposal=_guided(throttle, 75.0, LAUNCH_HEADING_DEG, message, _EFFECT_HOLD),
            situation=situation,
        )

    target_pitch, target_heading, mode = _attitude_target(
        alt_m,
        prograde_pitch=prograde_pitch,
        prograde_heading=prograde_heading,
    )
    coasting = apo is not None and apo >= APOAPSIS_COAST_M and alt_m >= COAST_ALT_M and (vspeed or 0.0) >= 0.0
    if coasting:
        message = (
            f"Apoapsis is above {APOAPSIS_COAST_M / 1000:.0f} km — coast, throttle idle, "
            f"holding heading {target_heading:.0f}°."
        )
        return _hold_or_sas(
            mode="coast",
            message=message,
            throttle=0.0,
            target_pitch=target_pitch,
            target_heading=target_heading,
            heading=heading,
            pitch=pitch,
            roll=roll,
            situation=situation,
        )

    throttle, limit = _powered_throttle(
        dyn=dyn,
        overheating=overheating,
        too_fast=too_fast,
        speed=speed,
        temp=temp,
        throttle_now=throttle_now,
    )
    if alt is None:
        message = _with_limit(
            "Vessel is flying but altitude is missing — shallow climb on heading 90°.",
            limit,
        )
        return FlightDecision(
            status="climb",
            message=message,
            proposal=_guided(
                min(throttle, 0.8),
                SHALLOW_CLIMB_PITCH_DEG,
                LAUNCH_HEADING_DEG,
                message,
                _EFFECT_HOLD,
            ),
            situation=situation,
        )

    if mode == "prograde":
        base = (
            f"Early ascent: holding surface prograde, pitch {target_pitch:.0f}° "
            f"heading {target_heading:.0f}°."
        )
    elif mode == "climb":
        base = (
            f"Early ascent: shallow climb pitch {target_pitch:.0f}° on heading {target_heading:.0f}° "
            "until prograde is a real climb."
        )
    else:
        base = f"Stable heading {target_heading:.0f}° east, pitch {target_pitch:.0f}°."
    if throttle >= 1.0:
        base = f"{base} Throttle full."
    elif limit is None and throttle < 1.0:
        base = f"{base} Dynamic pressure is high — throttle {throttle:.0%}."
    message = _with_limit(base, limit)
    return _hold_or_sas(
        mode=mode,
        message=message,
        throttle=throttle,
        target_pitch=target_pitch,
        target_heading=target_heading,
        heading=heading,
        pitch=pitch,
        roll=roll,
        situation=situation,
    )


def command_signature(decision: FlightDecision, *, staging: bool = False) -> tuple[object, ...]:
    """Coarse key so the blackboard updates when the setpoint actually changes."""
    if decision.proposal is None:
        return (decision.status, decision.message)
    params = decision.proposal.get("params")
    if not isinstance(params, dict):
        return (decision.status, decision.message)
    throttle = _as_float(params.get("throttle"))
    pitch = _as_float(params.get("pitch_deg"))
    heading = _as_float(params.get("heading_deg"))
    pitch_bucket = None if pitch is None else round(pitch / 5.0) * 5
    heading_bucket = None if heading is None else round(heading / 5.0) * 5
    throttle_bucket = None if throttle is None else round(throttle, 1)
    return (
        decision.status,
        throttle_bucket,
        pitch_bucket,
        heading_bucket,
        bool(params.get("sas", False)),
        staging,
    )


class FlightDecision:
    """One control tick. ``proposal`` is an ActionPropose-shaped dict, or None."""

    def __init__(
        self,
        *,
        status: str,
        message: str,
        proposal: dict[str, Any] | None = None,
        stage_once: bool = False,
        situation: str | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.proposal = proposal
        self.stage_once = stage_once
        self.situation = situation


def _hold_or_sas(
    *,
    mode: str,
    message: str,
    throttle: float,
    target_pitch: float,
    target_heading: float,
    heading: float | None,
    pitch: float | None,
    roll: float | None,
    situation: str | None,
) -> FlightDecision:
    """Steer until the nose is on the target, then leave SAS holding it."""
    if _aligned(heading, pitch, roll, target_heading, target_pitch):
        held = f"{message} Nose is there — SAS on, autopilot released so it does not hunt."
        return FlightDecision(
            status=mode,
            message=held,
            proposal=_sas_only(throttle, held),
            situation=situation,
        )
    return FlightDecision(
        status=mode,
        message=message,
        proposal=_guided(throttle, target_pitch, target_heading, message, _EFFECT_HOLD),
        situation=situation,
    )


def _attitude_target(
    alt_m: float,
    *,
    prograde_pitch: float | None,
    prograde_heading: float | None,
) -> tuple[float, float, str]:
    if alt_m < EARLY_ALT_M:
        if prograde_pitch is not None and prograde_pitch >= PROGRADE_MIN_PITCH_DEG:
            heading = LAUNCH_HEADING_DEG if prograde_heading is None else _bucket_deg(prograde_heading)
            return _bucket_deg(prograde_pitch), heading, "prograde"
        return SHALLOW_CLIMB_PITCH_DEG, LAUNCH_HEADING_DEG, "climb"
    return _ascent_pitch(alt_m), LAUNCH_HEADING_DEG, "heading"


def _powered_throttle(
    *,
    dyn: float | None,
    overheating: bool,
    too_fast: bool,
    speed: float | None,
    temp: float | None,
    throttle_now: float | None,
) -> tuple[float, str | None]:
    if overheating:
        hot = f"{temp:.0%} of max" if temp is not None else "hot"
        was = f" from {throttle_now:.0%}" if throttle_now is not None and throttle_now > 0.05 else ""
        return 0.0, f"Overheating ({hot}) — throttle cut{was}."
    if too_fast:
        shown = f"{speed:.0f} m/s" if speed is not None else "fast"
        return 0.0, f"Past a sensible speed ({shown} below {THICK_AIR_ALT_M / 1000:.0f} km) — throttle cut."
    if dyn is not None and dyn >= MAX_Q_PA:
        return MAX_Q_THROTTLE, None
    return 1.0, None


def _with_limit(message: str, limit: str | None) -> str:
    if limit is None:
        return message
    return f"{limit} {message}"


def _ascent_pitch(alt_m: float) -> float:
    """Gravity turn, quantized to 5° so the autopilot is not retargeted every metre."""
    if alt_m < TURN_START_M:
        return 90.0
    if alt_m >= TURN_END_M:
        return 5.0
    frac = (alt_m - TURN_START_M) / (TURN_END_M - TURN_START_M)
    raw = max(5.0, 90.0 * (1.0 - frac))
    return _bucket_deg(raw)


def _bucket_deg(value: float) -> float:
    return round(value / 5.0) * 5.0


def _aligned(
    heading: float | None,
    pitch: float | None,
    roll: float | None,
    target_heading: float,
    target_pitch: float,
) -> bool:
    if heading is None or pitch is None:
        return False
    if roll is not None and abs(_wrap180(roll)) > ROLL_TOL_DEG:
        return False
    if abs(_wrap180(heading - target_heading)) > HEADING_TOL_DEG:
        return False
    return abs(pitch - target_pitch) <= PITCH_TOL_DEG


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def _guided(throttle: float, pitch: float, heading: float, message: str, effect: str) -> dict[str, Any]:
    return {
        "action_id": "ksp.fly",
        "params": {
            "throttle": round(max(0.0, min(1.0, throttle)), 3),
            "sas": False,
            "pitch_deg": round(pitch, 1),
            "heading_deg": round(heading % 360.0, 1),
        },
        "rationale": message,
        "risk": "low",
        "expected_effect": effect,
    }


def _sas_only(throttle: float, message: str) -> dict[str, Any]:
    return {
        "action_id": "ksp.fly",
        "params": {
            "throttle": round(max(0.0, min(1.0, throttle)), 3),
            "sas": True,
            "sas_mode": "stability",
        },
        "rationale": message,
        "risk": "low",
        "expected_effect": _EFFECT_SAS,
    }


def _situation(vehicle: Mapping[str, Any]) -> str | None:
    raw = vehicle.get("situation")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _alt(vehicle: Mapping[str, Any]) -> float | None:
    geo = vehicle.get("geo")
    if not isinstance(geo, dict):
        return None
    return _as_float(geo.get("alt_m"))


def _vspeed(vehicle: Mapping[str, Any]) -> float | None:
    velocity = vehicle.get("velocity")
    if not isinstance(velocity, dict):
        return None
    return _as_float(velocity.get("vertical_mps"))


def _speed(vehicle: Mapping[str, Any]) -> float | None:
    velocity = vehicle.get("velocity")
    if not isinstance(velocity, dict):
        return None
    speed = _as_float(velocity.get("speed_mps"))
    if speed is not None:
        return abs(speed)
    vertical = _as_float(velocity.get("vertical_mps"))
    horizontal = _as_float(velocity.get("horizontal_mps"))
    if vertical is None and horizontal is None:
        return None
    return math.hypot(vertical or 0.0, horizontal or 0.0)


def _apoapsis(vehicle: Mapping[str, Any]) -> float | None:
    return _orbit_alt(vehicle, "apoapsis_m")


def _periapsis(vehicle: Mapping[str, Any]) -> float | None:
    return _orbit_alt(vehicle, "periapsis_m")


def _orbit_alt(vehicle: Mapping[str, Any], name: str) -> float | None:
    orbit = vehicle.get("orbit")
    if not isinstance(orbit, dict):
        return None
    return _as_float(orbit.get(name))


def _dynamic_pressure(frame: Mapping[str, Any]) -> float | None:
    env = frame.get("environment")
    if not isinstance(env, dict):
        return None
    return _as_float(env.get("dynamic_pressure_pa"))


def _angular_rate(vehicle: Mapping[str, Any]) -> float | None:
    return _as_float(vehicle.get("angular_rate_rad_s"))


def _throttle(vehicle: Mapping[str, Any]) -> float | None:
    controls = vehicle.get("controls")
    if not isinstance(controls, dict):
        return None
    return _as_float(controls.get("throttle"))


def _temp_ratio(vehicle: Mapping[str, Any]) -> float | None:
    engine = vehicle.get("engine")
    if not isinstance(engine, dict):
        return None
    return _as_float(engine.get("max_temp_ratio"))


def _axis(vehicle: Mapping[str, Any], name: str) -> float | None:
    attitude = vehicle.get("attitude")
    if isinstance(attitude, dict):
        value = _as_float(attitude.get(name))
        if value is not None:
            return value
    return _as_float(vehicle.get(name))


def _prograde(vehicle: Mapping[str, Any]) -> tuple[float | None, float | None]:
    pitch = _as_float(vehicle.get("prograde_pitch_deg"))
    heading = _as_float(vehicle.get("prograde_heading_deg"))
    if pitch is not None:
        return pitch, heading
    velocity = vehicle.get("velocity")
    if not isinstance(velocity, dict):
        return None, None
    vertical = _as_float(velocity.get("vertical_mps"))
    horizontal = _as_float(velocity.get("horizontal_mps"))
    if vertical is None or horizontal is None:
        return None, None
    if math.hypot(vertical, horizontal) < PROGRADE_MIN_MPS:
        return None, None
    return math.degrees(math.atan2(vertical, max(0.0, horizontal))), None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


_ORBIT_M = 70_000.0
_APO_TARGET_M = 80_000.0


def _decide_goal(frame: Mapping[str, Any], goal: FlightGoal) -> FlightDecision:
    """Fly one contract step. Does not fall through to the generic 80 km climb."""
    scene = str(frame.get("scene") or "").strip()
    if scene != "flight":
        shown = scene or "unknown"
        return FlightDecision(
            status="no_vessel",
            message=f"No active flight scene (scene={shown}). Load a vessel and launch — not steering.",
        )
    if bool(frame.get("paused")):
        return FlightDecision(status="paused", message="Flight is paused — not sending controls.")
    vehicle = frame.get("vehicle")
    if not isinstance(vehicle, dict):
        return FlightDecision(
            status="no_vessel",
            message="No active vessel in the flight scene — not steering.",
        )
    name = vehicle.get("name")
    named = isinstance(name, str) and bool(name.strip())
    alt = _alt(vehicle)
    situation = _situation(vehicle)
    if not named and alt is None:
        return FlightDecision(
            status="no_vessel",
            message="Flight scene has no active vessel — not steering.",
        )
    alt_m = 0.0 if alt is None else alt
    vspeed = _vspeed(vehicle)
    apo = _apoapsis(vehicle)
    peri = _periapsis(vehicle)
    pre_launch = situation == "pre_launch" or (
        situation is None and alt_m < TURN_START_M and (vspeed or 0) <= 0
    )
    return _goal_setpoint(
        goal,
        alt_m=alt_m,
        vspeed=vspeed,
        apo=apo,
        peri=peri,
        situation=situation,
        pre_launch=pre_launch,
    )


def _goal_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    apo: float | None,
    peri: float | None,
    situation: str | None,
    pre_launch: bool,
) -> FlightDecision:
    if goal.kind == "hold":
        return _goal_decision(
            "contract_hold",
            goal.summary or "Holding. Not launching until a contract step needs it.",
            throttle=0.0,
            sas=True,
            situation=situation,
        )
    if goal.kind == "part_test" and goal.situation in {"landed", "splashed"}:
        if situation in {"landed", "splashed", "pre_launch", None}:
            return _goal_decision(
                "contract_hold",
                _goal_text(goal, "Holding on the ground so the part test can complete. Not launching."),
                throttle=0.0,
                sas=True,
                situation=situation,
            )
        return _recover_setpoint(goal, alt_m=alt_m, vspeed=vspeed, apo=apo, peri=peri, situation=situation)
    if goal.kind == "recover" or (goal.kind == "part_test" and goal.situation == "escaping"):
        return _recover_setpoint(goal, alt_m=alt_m, vspeed=vspeed, apo=apo, peri=peri, situation=situation)
    if goal.kind == "orbit" or (goal.kind == "part_test" and goal.situation == "orbiting"):
        return _orbit_setpoint(
            goal,
            alt_m=alt_m,
            vspeed=vspeed,
            apo=apo,
            peri=peri,
            situation=situation,
            pre_launch=pre_launch,
        )
    if goal.kind == "suborbital" or (goal.kind == "part_test" and goal.situation == "sub_orbital"):
        return _suborbital_setpoint(
            goal,
            alt_m=alt_m,
            vspeed=vspeed,
            apo=apo,
            situation=situation,
            pre_launch=pre_launch,
        )
    if _has_band(goal) and goal.kind in {"altitude", "part_test"}:
        return _band_setpoint(
            goal,
            alt_m=alt_m,
            vspeed=vspeed,
            situation=situation,
            pre_launch=pre_launch,
        )
    if goal.kind == "part_test":
        return _flight_test_setpoint(
            goal,
            alt_m=alt_m,
            vspeed=vspeed,
            situation=situation,
            pre_launch=pre_launch,
        )
    return _altitude_setpoint(
        goal,
        alt_m=alt_m,
        vspeed=vspeed,
        apo=apo,
        situation=situation,
        pre_launch=pre_launch,
    )


def _altitude_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    apo: float | None,
    situation: str | None,
    pre_launch: bool,
) -> FlightDecision:
    target = goal.altitude_m if goal.altitude_m is not None else 5_000.0
    if alt_m >= target:
        return _goal_decision(
            "contract_hold",
            _goal_text(
                goal,
                f"Altitude {target:.0f} m is met — throttle idle until the parameter completes.",
            ),
            throttle=0.0,
            sas=True,
            situation=situation,
        )
    if pre_launch:
        return _goal_decision(
            "contract_launch",
            _goal_text(goal, f"Launching for {target:.0f} m. Throttle full, pitch 90°, heading 90° east."),
            throttle=1.0,
            pitch=90.0,
            heading=LAUNCH_HEADING_DEG,
            stage_once=True,
            situation=situation or "pre_launch",
        )
    if apo is not None and apo >= target and (vspeed or 0.0) > 0:
        return _goal_decision(
            "contract_coast",
            _goal_text(goal, "Apoapsis already clears the contract altitude — coasting up to it."),
            throttle=0.0,
            pitch=_ascent_pitch(alt_m),
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    pitch = _ascent_pitch(alt_m)
    return _goal_decision(
        "contract_ascent",
        _goal_text(goal, f"Climbing to {target:.0f} m, pitch {pitch:.0f}°, heading 90° east."),
        throttle=1.0,
        pitch=pitch,
        heading=LAUNCH_HEADING_DEG,
        situation=situation,
    )


def _orbit_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    apo: float | None,
    peri: float | None,
    situation: str | None,
    pre_launch: bool,
) -> FlightDecision:
    if peri is not None and apo is not None and peri >= _ORBIT_M and apo >= _ORBIT_M:
        return _goal_decision(
            "contract_hold",
            _goal_text(goal, "Periapsis and apoapsis are above the atmosphere — orbit step met."),
            throttle=0.0,
            sas=True,
            situation=situation,
        )
    if pre_launch:
        return _goal_decision(
            "contract_launch",
            _goal_text(goal, "Launching for orbit. Throttle full, pitch 90°, heading 90° east."),
            throttle=1.0,
            pitch=90.0,
            heading=LAUNCH_HEADING_DEG,
            stage_once=True,
            situation=situation or "pre_launch",
        )
    if apo is None or apo < _APO_TARGET_M:
        pitch = _ascent_pitch(alt_m)
        return _goal_decision(
            "contract_ascent",
            _goal_text(goal, f"Raising apoapsis toward {_APO_TARGET_M / 1000:.0f} km, pitch {pitch:.0f}°."),
            throttle=1.0,
            pitch=pitch,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    near_apo = (vspeed is not None and abs(vspeed) < 40.0) or alt_m >= apo - 2_500.0
    if (peri is None or peri < _ORBIT_M) and near_apo and alt_m >= 60_000.0:
        return _goal_decision(
            "contract_circularize",
            _goal_text(goal, "Circularizing at apoapsis until periapsis clears the atmosphere."),
            throttle=1.0,
            pitch=5.0,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    pitch = _ascent_pitch(alt_m)
    return _goal_decision(
        "contract_coast",
        _goal_text(goal, "Coasting to apoapsis before the circularization burn."),
        throttle=0.0,
        pitch=pitch,
        heading=LAUNCH_HEADING_DEG,
        situation=situation,
    )


def _suborbital_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    apo: float | None,
    situation: str | None,
    pre_launch: bool,
) -> FlightDecision:
    del vspeed
    if apo is not None and apo >= _ORBIT_M:
        return _goal_decision(
            "contract_coast",
            _goal_text(goal, "Apoapsis is above the atmosphere — coasting the sub-orbital arc."),
            throttle=0.0,
            pitch=_ascent_pitch(alt_m),
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    if pre_launch:
        return _goal_decision(
            "contract_launch",
            _goal_text(goal, "Launching onto a sub-orbital arc. Throttle full, pitch 90°."),
            throttle=1.0,
            pitch=90.0,
            heading=LAUNCH_HEADING_DEG,
            stage_once=True,
            situation=situation or "pre_launch",
        )
    pitch = _ascent_pitch(alt_m)
    return _goal_decision(
        "contract_ascent",
        _goal_text(goal, f"Climbing for a sub-orbital arc, pitch {pitch:.0f}°."),
        throttle=1.0,
        pitch=pitch,
        heading=LAUNCH_HEADING_DEG,
        situation=situation,
    )


def _band_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    situation: str | None,
    pre_launch: bool,
) -> FlightDecision:
    lo = goal.altitude_min_m if goal.altitude_min_m is not None else 0.0
    hi = goal.altitude_max_m if goal.altitude_max_m is not None else lo
    if pre_launch and alt_m < lo:
        return _goal_decision(
            "contract_launch",
            _goal_text(goal, f"Launching into the {lo:.0f}-{hi:.0f} m band."),
            throttle=1.0,
            pitch=90.0,
            heading=LAUNCH_HEADING_DEG,
            stage_once=True,
            situation=situation or "pre_launch",
        )
    if alt_m < lo:
        pitch = _ascent_pitch(alt_m)
        return _goal_decision(
            "contract_ascent",
            _goal_text(goal, f"Climbing to the {lo:.0f}-{hi:.0f} m band, pitch {pitch:.0f}°."),
            throttle=1.0,
            pitch=pitch,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    if alt_m > hi:
        return _goal_decision(
            "contract_coast",
            _goal_text(
                goal,
                "Above the contract band — throttle idle so the vessel can settle back into it.",
            ),
            throttle=0.0,
            pitch=15.0,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    climbing = vspeed is not None and vspeed < 0
    return _goal_decision(
        "contract_hold",
        _goal_text(goal, f"Inside {lo:.0f}-{hi:.0f} m. Holding the band for the contract."),
        throttle=0.85 if climbing else 0.4,
        pitch=55.0 if climbing else 25.0,
        heading=LAUNCH_HEADING_DEG,
        situation=situation,
    )


def _flight_test_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    situation: str | None,
    pre_launch: bool,
) -> FlightDecision:
    if pre_launch:
        return _goal_decision(
            "contract_launch",
            _goal_text(goal, "Launching so the part test is in flight."),
            throttle=1.0,
            pitch=90.0,
            heading=LAUNCH_HEADING_DEG,
            stage_once=True,
            situation=situation or "pre_launch",
        )
    if situation in {"flying", "sub_orbital", "orbiting"} and alt_m > 250:
        dropping = vspeed is not None and vspeed < 0
        return _goal_decision(
            "contract_hold",
            _goal_text(goal, "In flight for the part test — keeping the engine running."),
            throttle=0.8 if dropping else 0.45,
            pitch=60.0 if dropping else 35.0,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    pitch = _ascent_pitch(alt_m)
    return _goal_decision(
        "contract_ascent",
        _goal_text(goal, f"Climbing into flight for the part test, pitch {pitch:.0f}°."),
        throttle=1.0,
        pitch=pitch,
        heading=LAUNCH_HEADING_DEG,
        situation=situation,
    )


def _recover_setpoint(
    goal: FlightGoal,
    *,
    alt_m: float,
    vspeed: float | None,
    apo: float | None,
    peri: float | None,
    situation: str | None,
) -> FlightDecision:
    if situation in {"landed", "splashed", "pre_launch"}:
        return _goal_decision(
            "contract_recover",
            _goal_text(goal, "On the ground. Recover the vessel to finish this step."),
            throttle=0.0,
            sas=True,
            situation=situation,
        )
    if peri is not None and peri >= 60_000 and (apo or 0.0) >= 60_000:
        return _goal_decision(
            "contract_deorbit",
            _goal_text(goal, "Deorbit burn, heading west, so the vessel can be recovered."),
            throttle=1.0,
            pitch=0.0,
            heading=270.0,
            situation=situation,
        )
    if alt_m > 2_500:
        return _goal_decision(
            "contract_descend",
            _goal_text(goal, "Coasting down to recover the vessel."),
            throttle=0.0,
            pitch=20.0,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    if vspeed is not None and vspeed < RECOVER_VS_MPS:
        return _goal_decision(
            "contract_recover",
            _goal_text(goal, "Low and fast — pitching up so the recovery does not hit hard."),
            throttle=1.0,
            pitch=75.0,
            heading=LAUNCH_HEADING_DEG,
            situation=situation,
        )
    return _goal_decision(
        "contract_descend",
        _goal_text(goal, "Final descent for recovery."),
        throttle=0.0,
        pitch=45.0,
        heading=LAUNCH_HEADING_DEG,
        situation=situation,
    )


def _has_band(goal: FlightGoal) -> bool:
    return goal.altitude_min_m is not None and goal.altitude_max_m is not None


def _goal_text(goal: FlightGoal, detail: str) -> str:
    if not goal.contract_title:
        return detail
    return f"{goal.contract_title}: {detail}"


def _goal_decision(
    status: str,
    message: str,
    *,
    throttle: float,
    situation: str | None,
    pitch: float | None = None,
    heading: float | None = None,
    sas: bool = False,
    stage_once: bool = False,
) -> FlightDecision:
    if pitch is None or heading is None:
        proposal = _sas_only(throttle, message)
    else:
        proposal = _guided(throttle, pitch, heading, message, _EFFECT_HOLD)
    return FlightDecision(
        status=status,
        message=message,
        proposal=proposal,
        stage_once=stage_once,
        situation=situation,
    )
