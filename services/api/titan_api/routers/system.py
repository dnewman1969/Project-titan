"""System routes (Section 5.2, "System").

`/system/status` merges the supervisor's process table with dependency checks run here, each
bounded to one second, so the call stays fast when something is down.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Literal

import redis.asyncio as aioredis
import redis.exceptions
from fastapi import APIRouter, Request
from pydantic import BaseModel

from titan_api.auth import Authenticated
from titan_api.supervisor_client import SupervisorProbe
from titan_core.errors import ErrorCode, TitanError
from titan_core.health import Check, timed
from titan_core.protocol.system import ServiceState, SupervisorStatus, SystemStatus
from titan_core.protocol.ws import SystemMetrics
from titan_core.streams import SYS_METRICS, latest_entry

CHECK_TIMEOUT_S = 1.0


class Health(BaseModel):
    status: Literal["ok"] = "ok"


public = APIRouter(tags=["system"])
router = APIRouter(prefix="/system", tags=["system"], dependencies=[Authenticated])


@public.get("/health")
async def health() -> Health:
    """Liveness probe. The only unauthenticated route."""
    return Health()


def _self_only(started_at: datetime) -> list[ServiceState]:
    """Without a supervisor (API started by hand) report just this process."""
    return [ServiceState(name="api", state="up", pid=os.getpid(), restarts=0, since=started_at)]


@router.get("/status")
async def system_status(request: Request) -> SystemStatus:
    checks: Mapping[str, Check] = request.app.state.dependency_checks
    probe_supervisor: SupervisorProbe = request.app.state.probe_supervisor
    supervisor_task: asyncio.Future[SupervisorStatus | None] = asyncio.ensure_future(probe_supervisor())
    states = await asyncio.gather(*(timed(check, CHECK_TIMEOUT_S) for check in checks.values()))
    supervisor = await supervisor_task
    started_at: datetime = request.app.state.started_at
    services = supervisor.services if supervisor is not None else _self_only(started_at)
    return SystemStatus(services=services, dependencies=dict(zip(checks, states, strict=True)))


@router.get("/metrics")
async def system_metrics(request: Request) -> SystemMetrics:
    """The newest `titan:sys:metrics` sample. Live updates come over WS `system.metrics`."""
    client: aioredis.Redis = request.app.state.redis
    try:
        latest = await latest_entry(client, SYS_METRICS)
    except (redis.exceptions.RedisError, OSError) as exc:
        raise TitanError(
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            f"Redis is unavailable ({type(exc).__name__}).",
            dependency="redis",
        ) from exc
    if latest is None:
        raise TitanError(ErrorCode.NOT_FOUND, "No metrics yet: the supervisor publishes them once a second.")
    return SystemMetrics.model_validate_json(latest[1])
