"""One vessel snapshot from a kRPC-shaped connection.

Duck-typed so unit tests pass a fake. The live caller is the kRPC Python client
already used by titan-actions. This does not require kOS or MechJeb.
"""

from __future__ import annotations

from typing import Any

_SCENE = {
    "flight": "flight",
    "space_center": "space_center",
    "tracking_station": "tracking",
    "editor_vab": "vab",
    "editor_sph": "sph",
}


def sample_vessel(conn: Any) -> dict[str, Any]:
    """Return a raw telemetry dict. No active flight vessel → ``scene`` is not ``flight``."""
    scene = _scene_name(conn)
    paused = _paused(conn)
    vessel = _active_vessel(conn)
    if vessel is None or scene != "flight":
        shown = scene if scene and scene != "flight" else "no_vessel"
        return {
            "scene": shown,
            "paused": paused,
            "situation": None,
            "vessel_present": False,
        }
    try:
        return _vessel_raw(vessel, scene=scene, paused=paused)
    except Exception:
        return {
            "scene": "no_vessel",
            "paused": paused,
            "situation": None,
            "vessel_present": False,
        }


def _vessel_raw(vessel: Any, *, scene: str, paused: bool) -> dict[str, Any]:
    ref = getattr(vessel, "surface_reference_frame", None)
    try:
        flight = vessel.flight(ref) if ref is not None else vessel.flight()
    except Exception:
        flight = vessel.flight()
    control = vessel.control
    orbit = getattr(vessel, "orbit", None)
    name = getattr(vessel, "name", None)
    raw: dict[str, Any] = {
        "scene": scene,
        "paused": paused,
        "vessel_present": True,
        "situation": _enum_name(getattr(vessel, "situation", None)),
        "vessel_name": name if isinstance(name, str) and name else None,
    }
    alt = _num(flight, "mean_altitude")
    if alt is not None:
        raw["mean_altitude_m"] = alt
        raw["latitude_deg"] = _num(flight, "latitude") or 0.0
        raw["longitude_deg"] = _num(flight, "longitude") or 0.0
    for src, dest in (
        ("speed", "speed_mps"),
        ("vertical_speed", "vertical_speed_mps"),
        ("horizontal_speed", "horizontal_speed_mps"),
        ("g_force", "accel_g"),
        ("dynamic_pressure", "dynamic_pressure_pa"),
        ("static_pressure", "static_pressure_pa"),
        ("atmosphere_density", "atmosphere_density"),
        ("heading", "heading_deg"),
        ("pitch", "pitch_deg"),
        ("roll", "roll_deg"),
    ):
        value = _num(flight, src)
        if value is not None:
            raw[dest] = value
    sas = _bool(control, "sas")
    if sas is not None:
        raw["sas"] = sas
    rcs = _bool(control, "rcs")
    if rcs is not None:
        raw["rcs"] = rcs
    throttle = _num(control, "throttle")
    if throttle is not None:
        raw["throttle"] = throttle
    stage = _num(control, "current_stage")
    if stage is not None:
        raw["stage_current"] = int(stage)
    if orbit is not None:
        apo = _num(orbit, "apoapsis_altitude")
        if apo is not None:
            # kRPC apoapsis_altitude is metres above sea level, not orbital radius.
            raw["apoapsis_altitude_m"] = apo
        peri = _num(orbit, "periapsis_altitude")
        if peri is not None:
            raw["periapsis_altitude_m"] = peri
        inc = _num(orbit, "inclination")
        if inc is not None:
            raw["inclination_deg"] = inc
        ecc = _num(orbit, "eccentricity")
        if ecc is not None:
            raw["eccentricity"] = ecc
        body = getattr(orbit, "body", None)
        body_name = getattr(body, "name", None)
        if isinstance(body_name, str) and body_name:
            raw["body"] = body_name
    return raw


def _active_vessel(conn: Any) -> Any:
    try:
        return conn.space_center.active_vessel
    except Exception:
        return None


def _scene_name(conn: Any) -> str:
    try:
        raw = conn.krpc.current_game_scene
    except Exception:
        return "no_vessel"
    name = _enum_name(raw) or "no_vessel"
    return _SCENE.get(name, name)


def _paused(conn: Any) -> bool:
    try:
        return bool(conn.krpc.paused)
    except Exception:
        return False


def _enum_name(value: Any) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.lower()
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.strip().lower()
    return text or None


def _num(obj: Any, name: str) -> float | None:
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _bool(obj: Any, name: str) -> bool | None:
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if isinstance(value, bool):
        return value
    return None
