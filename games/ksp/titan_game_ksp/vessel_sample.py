"""One vessel snapshot from a kRPC-shaped connection.

Duck-typed so unit tests pass a fake. The live caller is the kRPC Python client
already used by titan-actions. This does not require kOS or MechJeb.
"""

from __future__ import annotations

import math
import time
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
    rate = _angular_rate(vessel, ref)
    if rate is not None:
        raw["angular_rate_rad_s"] = rate
    prograde_pitch, prograde_heading = _surface_prograde(vessel, ref)
    if prograde_pitch is not None:
        raw["prograde_pitch_deg"] = prograde_pitch
    if prograde_heading is not None:
        raw["prograde_heading_deg"] = prograde_heading
    hottest = _max_temp_ratio(vessel)
    if hottest is not None:
        raw["max_temp_ratio"] = hottest
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


def _angular_rate(vessel: Any, ref: Any) -> float | None:
    """Magnitude of ``vessel.angular_velocity`` in rad/s (kRPC surface frame)."""
    fn = getattr(vessel, "angular_velocity", None)
    if not callable(fn):
        return None
    try:
        vector = fn(ref) if ref is not None else fn()
    except TypeError:
        try:
            vector = fn()
        except Exception:
            return None
    except Exception:
        return None
    return _magnitude(vector)


def _surface_prograde(vessel: Any, ref: Any) -> tuple[float | None, float | None]:
    """Pitch and heading of surface velocity.

    kRPC ``vessel.surface_reference_frame`` is (up, north, east). Prograde is
    undefined when the vessel is barely moving — the same case kOS refuses to
    ``lock steering to srfprograde``.
    """
    fn = getattr(vessel, "velocity", None)
    if not callable(fn) or ref is None:
        return None, None
    try:
        vector = fn(ref)
    except Exception:
        return None, None
    parsed = _vec3(vector)
    if parsed is None:
        return None, None
    up, north, east = parsed
    horizontal = math.hypot(north, east)
    if horizontal < 1.0 and abs(up) < 1.0:
        return None, None
    pitch = math.degrees(math.atan2(up, horizontal))
    heading = math.degrees(math.atan2(east, north)) % 360.0
    return pitch, heading


_HEAT_CACHE: tuple[float, float] | None = None
_HEAT_PERIOD_S = 1.0


def _max_temp_ratio(vessel: Any) -> float | None:
    """Hottest part temperature / max, including skin.

    Part temperature is an RPC per part, so this walks engines first (the parts
    that actually cook under throttle), caps the walk, and reuses the result for
    a second. The flight loop only needs it at 1 Hz.
    """
    global _HEAT_CACHE
    now = time.monotonic()
    if _HEAT_CACHE is not None and now - _HEAT_CACHE[0] < _HEAT_PERIOD_S:
        return _HEAT_CACHE[1]
    value = _scan_heat(vessel)
    if value is not None:
        _HEAT_CACHE = (now, value)
    return value


def _scan_heat(vessel: Any) -> float | None:
    parts = getattr(vessel, "parts", None)
    if parts is None:
        return None
    listed = _heat_parts(parts)
    best: float | None = None
    for part in listed[:16]:
        for num_name, den_name in (
            ("temperature", "max_temperature"),
            ("skin_temperature", "max_skin_temperature"),
            ("skin_temperature", "skin_max_temperature"),
        ):
            value = _ratio(part, num_name, den_name)
            if value is None:
                continue
            best = value if best is None else max(best, value)
    return best


def _heat_parts(parts: Any) -> list[Any]:
    engines = getattr(parts, "engines", None)
    found: list[Any] = []
    if engines is not None:
        try:
            for engine in list(engines)[:16]:
                part = getattr(engine, "part", None)
                found.append(engine if part is None else part)
        except Exception:
            found = []
    if found:
        return found
    try:
        all_parts = getattr(parts, "all", None)
        if all_parts is None:
            return []
        return list(all_parts)
    except Exception:
        return []


def _ratio(obj: Any, num_name: str, den_name: str) -> float | None:
    num = _num(obj, num_name)
    den = _num(obj, den_name)
    if num is None or den is None or den <= 0.0:
        return None
    return num / den


def _magnitude(vector: Any) -> float | None:
    parsed = _vec3(vector)
    if parsed is None:
        return None
    x, y, z = parsed
    return math.sqrt(x * x + y * y + z * z)


def _vec3(value: Any) -> tuple[float, float, float] | None:
    if isinstance(value, (str, bytes)) or value is None:
        return None
    try:
        items = list(value)
    except TypeError:
        return None
    if len(items) < 3:
        return None
    nums: list[float] = []
    for item in items[:3]:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        nums.append(float(item))
    return nums[0], nums[1], nums[2]


def _bool(obj: Any, name: str) -> bool | None:
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if isinstance(value, bool):
        return value
    return None
