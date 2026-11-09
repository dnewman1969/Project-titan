"""Normalized telemetry schema `titan.telemetry/1` (Section 7.2).

Units are SI (m, m/s, kg, L, Pa, degrees C, s); angles in degrees; ratios 0..1. Missing values
are `null` and never fabricated, so every field is required but most are nullable.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from titan_core.protocol.common import Domain, ProtocolModel

TELEMETRY_SCHEMA = "titan.telemetry/1"


class Position(ProtocolModel):
    frame: str = Field(description="ksp: body-centred 'body:<name>'; scs: 'scs_world' metres")
    x: float
    y: float
    z: float


class Geo(ProtocolModel):
    lat_deg: float
    lon_deg: float
    alt_m: float


class Attitude(ProtocolModel):
    heading_deg: float
    pitch_deg: float
    roll_deg: float


class Velocity(ProtocolModel):
    speed_mps: float
    vertical_mps: float | None
    horizontal_mps: float | None


class Controls(ProtocolModel):
    throttle: float | None
    brake: float | None
    steer: float | None
    clutch: float | None
    gear: int | None
    sas: bool | None
    rcs: bool | None
    parking_brake: bool | None
    cruise_control_mps: float | None
    lights: str | None


class Engine(ProtocolModel):
    running: bool | None
    rpm: float | None
    temp_c: float | None
    max_temp_ratio: float | None


class Damage(ProtocolModel):
    overall: float | None = Field(description="0 = pristine, 1 = destroyed")
    parts: dict[str, float]


class Stage(ProtocolModel):
    current: int
    total: int | None
    dv_ms: float | None


class Orbit(ProtocolModel):
    body: str
    apoapsis_m: float
    periapsis_m: float
    inclination_deg: float
    eccentricity: float
    period_s: float | None
    time_to_apoapsis_s: float | None
    time_to_periapsis_s: float | None
    time_to_soi_change_s: float | None


class Vehicle(ProtocolModel):
    name: str | None
    kind: str | None = Field(description="'rocket', 'truck', ...")
    position: Position | None
    geo: Geo | None
    attitude: Attitude | None
    velocity: Velocity | None
    accel_g: float | None
    controls: Controls | None
    engine: Engine | None
    damage: Damage | None
    situation: str | None = Field(
        description="ksp: pre_launch|flying|sub_orbital|orbiting|escaping|landed|splashed|docked"
    )
    stage: Stage | None
    orbit: Orbit | None
    angular_rate_rad_s: float | None = Field(
        default=None,
        description="Magnitude of angular velocity in rad/s. Null when the adapter did not read it.",
    )
    prograde_pitch_deg: float | None = Field(
        default=None,
        description="Surface-prograde pitch in degrees. Null when velocity is too small to define it.",
    )
    prograde_heading_deg: float | None = Field(
        default=None,
        description="Surface-prograde heading in degrees. Null when velocity is too small to define it.",
    )


class Resource(ProtocolModel):
    id: str
    name: str
    amount: float
    capacity: float
    unit: str
    scope: Literal["vehicle", "stage", "trailer"]


class Environment(ProtocolModel):
    body: str | None
    atmosphere_density: float | None
    dynamic_pressure_pa: float | None
    static_pressure_pa: float | None
    speed_limit_mps: float | None
    weather: str | None
    local_time: str | None


class Job(ProtocolModel):
    active: bool
    cargo: str | None
    mass_kg: float | None
    source: str | None
    destination: str | None
    income: float | None
    currency: str | None
    deadline_game_s: float | None
    nav_distance_m: float | None
    nav_time_s: float | None
    trailer_attached: bool | None
    cargo_damage: float | None


class Economy(ProtocolModel):
    funds: float | None
    science: float | None
    reputation: float | None
    currency: str | None


class TelemetryFrameUI(ProtocolModel):
    """`TelemetryFrame` without `game_specific`: what the UI receives on the telemetry channel."""

    schema_: Literal["titan.telemetry/1"] = Field(alias="schema")
    session_id: UUID
    game: str = Field(description="'ksp' | 'ets2' | 'ats' | ...")
    adapter_version: str
    seq: int = Field(ge=0, description="Per session, monotonic")
    t_mono_ns: int
    t_session_ms: int
    t_game_s: float | None = Field(description="KSP UT seconds; SCS game time in seconds")
    paused: bool
    scene: str = Field(
        description="ksp: flight|map|vab|sph|space_center|tracking|menu ; scs: driving|menu|loading|map"
    )
    domain: Domain
    vehicle: Vehicle
    resources: list[Resource]
    environment: Environment | None
    job: Job | None
    economy: Economy | None


class TelemetryFrame(TelemetryFrameUI):
    game_specific: dict[str, Any] = Field(
        description="Adapter-defined, documented in the game package README"
    )
