"""Internal HTTP endpoint on 127.0.0.1:8769 (Section 2.3), bearer-authenticated with the launch token.

Used by Electron (boot splash, shutdown), the API (`/system/status`) and later the session
controller (start/stop session processes, PresentMon target).
"""

from __future__ import annotations

import contextlib
import secrets
import socket
import sys
from collections.abc import Callable, Generator
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from titan_core.protocol.system import GameTarget, SupervisorStatus
from titan_core.protocol.ws import SystemMetrics
from titan_supervisor.core import Supervisor
from titan_supervisor.metrics import MetricsSampler

_bearer = HTTPBearer(auto_error=False)


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Accepted(BaseModel):
    accepted: Literal[True] = True


def create_app(
    supervisor: Supervisor,
    *,
    token: str,
    sampler: MetricsSampler | None = None,
    on_shutdown: Callable[[], None] = lambda: None,
) -> FastAPI:
    def require_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), token.encode()
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing bearer token")

    app = FastAPI(title="titan-supervisor", openapi_url=None, docs_url=None, redoc_url=None)
    auth = [Depends(require_token)]

    @app.get("/health")
    async def health() -> Health:
        return Health()

    @app.get("/status", dependencies=auth)
    async def get_status(since: int = 0) -> SupervisorStatus:
        snapshot = supervisor.status()
        if since:
            snapshot.events = [e for e in snapshot.events if e.seq > since]
        return snapshot

    @app.post("/processes/{name}/restart", dependencies=auth, status_code=202)
    async def restart(name: str, request: Request) -> Accepted:
        if name not in supervisor.names:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown process {name!r}")
        await supervisor.restart(name)
        return Accepted()

    @app.get("/metrics/latest", dependencies=auth)
    async def latest_metrics() -> SystemMetrics:
        if sampler is None or sampler.latest is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no metrics sampled yet")
        return sampler.latest

    @app.put("/metrics/game", dependencies=auth)
    async def track_game(target: GameTarget) -> GameTarget:
        if sampler is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "metrics are disabled")
        await sampler.presentmon.track(target.pid)
        return target

    @app.post("/shutdown", dependencies=auth, status_code=202)
    async def shutdown() -> Accepted:
        on_shutdown()
        return Accepted()

    return app


class EmbeddedServer(uvicorn.Server):
    """uvicorn inside the supervisor's event loop. The supervisor owns signal handling."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield


def bind(host: str, port: int) -> socket.socket:
    """Bind the endpoint before starting anything: a second supervisor fails here, not halfway."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # Otherwise another process could bind the same port with SO_REUSEADDR and take requests.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    sock.listen(64)
    sock.set_inheritable(False)
    return sock


def embedded_server(app: FastAPI) -> EmbeddedServer:
    return EmbeddedServer(uvicorn.Config(app, log_config=None, access_log=False, lifespan="off"))
