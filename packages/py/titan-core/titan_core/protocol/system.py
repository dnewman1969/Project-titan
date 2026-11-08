"""System status, supervisor process table and safety requests (Sections 2.3 and 5.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from titan_core.protocol.common import ProtocolModel
from titan_core.protocol.ws import ResourceGuardLevel

ServiceStateName = Literal["up", "down", "starting", "degraded", "failed", "stopped", "unknown"]
"""`failed`: the restart circuit breaker is open. `stopped`: stopped on purpose."""

ProcessKind = Literal["managed", "external", "oneshot"]
"""`managed`: started and restarted by the supervisor. `external`: health-checked only (Memurai,
or a server someone else runs). `oneshot`: runs to completion once per start (migrations)."""

SupervisorEventKind = Literal[
    "starting", "healthy", "unhealthy", "exited", "restarting", "circuit_open", "stopped", "adopted"
]


class DependencyState(ProtocolModel):
    state: ServiceStateName
    version: str | None = None
    detail: str | None = None


class ServiceState(ProtocolModel):
    name: str
    state: ServiceStateName
    pid: int | None = None
    restarts: int = Field(default=0, ge=0)
    since: datetime | None = Field(default=None, description="When the current state began")
    detail: str | None = None
    kind: ProcessKind = "managed"


class SystemStatus(ProtocolModel):
    """`GET /system/status`."""

    services: list[ServiceState]
    dependencies: dict[str, DependencyState]
    resource_guard_level: ResourceGuardLevel = "L0"


class SupervisorEvent(ProtocolModel):
    seq: int = Field(ge=1, description="Increases by one per event; use it to fetch only new events")
    ts: datetime
    process: str
    kind: SupervisorEventKind
    detail: str | None = None


class SupervisorStatus(ProtocolModel):
    """`GET /status` on the supervisor's internal endpoint (127.0.0.1:8769)."""

    started_at: datetime
    ready: bool = Field(description="Every process in the start order has been healthy at least once")
    services: list[ServiceState]
    events: list[SupervisorEvent] = Field(description="Most recent events, oldest first")


class GameTarget(ProtocolModel):
    """`PUT /metrics/game` on the supervisor: the process PresentMon tracks (null stops tracking)."""

    pid: int | None = Field(ge=1)


class SafetyKillRequest(ProtocolModel):
    source: str = Field(min_length=1, max_length=32, description="hotkey, button, voice, api, ...")


class SafetyResumeRequest(ProtocolModel):
    confirm: Literal["RESUME"]


class SafetyArmRequest(ProtocolModel):
    session_id: str
    confirm: Literal["ARM"]
