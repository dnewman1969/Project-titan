"""Continuous KSP setpoints: throttle, SAS, and a heading hold.

kRPC (the control mod we already require) ships an autopilot that holds pitch and
heading until the next call — the same idea as kOS ``lock steering to heading()``
and the kRPC "launch into orbit" tutorial (pitch 90° until 250 m, then a linear
gravity turn, heading 90° east, throttle cut once apoapsis is high enough).
MechJeb and kOS are not required; this repo has no hooks for them.

``ksp.fly`` is re-sent about once a second so the hold is a loop, not a one-shot
poke of ``control.pitch``. SAS is released while the autopilot is engaged because
kRPC will not run both. On the ground, in orbit, or when there is no flight
scene, the decision is explicit and does not command a heading.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

LAUNCH_HEADING_DEG = 90.0
TURN_START_M = 250.0
TURN_END_M = 45_000.0
APOAPSIS_COAST_M = 80_000.0
COAST_ALT_M = 30_000.0
RECOVER_ALT_M = 800.0
RECOVER_VS_MPS = -15.0
MAX_Q_PA = 25_000.0
MAX_Q_THROTTLE = 0.65

_EFFECT_HOLD = "Autopilot holds pitch and heading; throttle follows the ascent."
_EFFECT_SAS = "Throttle and SAS only — autopilot released."


@dataclass(frozen=True)
class FlightDecision:
    """One control tick. ``proposal`` is an ActionPropose-shaped dict, or None."""

    status: str
    message: str
    proposal: dict[str, Any] | None = None
    stage_once: bool = False
    situation: str | None = None


def decide_flight(frame: Mapping[str, Any]) -> FlightDecision:
    """Choose the next KSP setpoint from a telemetry frame dict."""
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

    recovering = (
        situation not in {"pre_launch", "landed", "splashed"}
        and alt_m < RECOVER_ALT_M
        and vspeed is not None
        and vspeed < RECOVER_VS_MPS
    )
    if recovering:
        message = (
            "Low and descending — full throttle and pitch 75° on heading 90° "
            "so the vessel does not hit the ground."
        )
        return FlightDecision(
            status="recover",
            message=message,
            proposal=_guided(1.0, 75.0, LAUNCH_HEADING_DEG, message, _EFFECT_HOLD),
            situation=situation,
        )

    pitch = _ascent_pitch(alt_m)
    coasting = apo is not None and apo >= APOAPSIS_COAST_M and alt_m >= COAST_ALT_M and (vspeed or 0.0) >= 0.0
    if coasting:
        message = (
            f"Apoapsis is above {APOAPSIS_COAST_M / 1000:.0f} km — coast, throttle idle, "
            f"holding heading {LAUNCH_HEADING_DEG:.0f}°."
        )
        return FlightDecision(
            status="coast",
            message=message,
            proposal=_guided(0.0, pitch, LAUNCH_HEADING_DEG, message, _EFFECT_HOLD),
            situation=situation,
        )

    throttle = MAX_Q_THROTTLE if dyn is not None and dyn >= MAX_Q_PA else 1.0
    if alt is None:
        message = "Vessel is flying but altitude is missing — gentle climb on heading 90°."
        return FlightDecision(
            status="ascent",
            message=message,
            proposal=_guided(0.8, 80.0, LAUNCH_HEADING_DEG, message, _EFFECT_HOLD),
            situation=situation,
        )
    if throttle < 1.0:
        message = (
            f"Dynamic pressure is high — throttle {throttle:.0%}, pitch {pitch:.0f}° "
            f"toward heading {LAUNCH_HEADING_DEG:.0f}°."
        )
    else:
        message = (
            f"Ascent hold: throttle full, pitch {pitch:.0f}° toward heading {LAUNCH_HEADING_DEG:.0f}° east."
        )
    return FlightDecision(
        status="ascent",
        message=message,
        proposal=_guided(throttle, pitch, LAUNCH_HEADING_DEG, message, _EFFECT_HOLD),
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


def _ascent_pitch(alt_m: float) -> float:
    """Gravity turn: vertical until ``TURN_START_M``, near-horizon by ``TURN_END_M``."""
    if alt_m < TURN_START_M:
        return 90.0
    if alt_m >= TURN_END_M:
        return 5.0
    frac = (alt_m - TURN_START_M) / (TURN_END_M - TURN_START_M)
    return max(5.0, 90.0 * (1.0 - frac))


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
        "params": {"throttle": round(max(0.0, min(1.0, throttle)), 3), "sas": True},
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


def _apoapsis(vehicle: Mapping[str, Any]) -> float | None:
    orbit = vehicle.get("orbit")
    if not isinstance(orbit, dict):
        return None
    return _as_float(orbit.get("apoapsis_m"))


def _dynamic_pressure(frame: Mapping[str, Any]) -> float | None:
    env = frame.get("environment")
    if not isinstance(env, dict):
        return None
    return _as_float(env.get("dynamic_pressure_pa"))


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
