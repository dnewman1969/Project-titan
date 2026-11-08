"""System routes (Section 5.2, "System").

`/system/status` is a skeleton: it reports this API process and probes Postgres. The
supervisor's process table (M1.T3) and dependency checks for Redis, Chroma, Ollama and OBS
(M1.T2) fill in the rest.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from titan_api.auth import Authenticated

ServiceStateName = Literal["up", "down", "starting", "degraded", "unknown"]


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class ServiceState(BaseModel):
    name: str
    state: ServiceStateName
    pid: int | None = None
    restarts: int = 0
    since: datetime | None = None


class DependencyState(BaseModel):
    state: ServiceStateName
    version: str | None = None
    detail: str | None = None


class SystemStatus(BaseModel):
    services: list[ServiceState]
    dependencies: dict[str, DependencyState]
    resource_guard_level: Literal["L0", "L1", "L2", "L3", "L4"] = "L0"


public = APIRouter(tags=["system"])
router = APIRouter(prefix="/system", tags=["system"], dependencies=[Authenticated])


@public.get("/health")
async def health() -> Health:
    """Liveness probe. The only unauthenticated route."""
    return Health()


@router.get("/status")
async def system_status(request: Request) -> SystemStatus:
    started_at: datetime = request.app.state.started_at
    postgres = await request.app.state.probe_postgres()
    return SystemStatus(
        services=[ServiceState(name="api", state="up", pid=os.getpid(), restarts=0, since=started_at)],
        dependencies={"postgres": postgres},
    )
