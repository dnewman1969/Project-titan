"""App factory, routers, middleware and lifespan (Section 3, `services/api/titan_api/main.py`)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from titan_api import API_PREFIX
from titan_api.auth import launch_token_from_env
from titan_api.errors import install_error_handlers
from titan_api.routers import system
from titan_core.clock import utc_now
from titan_core.config import PostgresConfig, TitanConfig, load_config
from titan_core.logging import get_logger

log = get_logger(__name__)

PostgresProbe = Callable[[], Awaitable[system.DependencyState]]


def postgres_probe(pg: PostgresConfig, timeout_s: float = 1.0) -> PostgresProbe:
    """Return a coroutine function that reports whether Postgres accepts connections."""

    async def probe() -> system.DependencyState:
        try:
            conn = await asyncpg.connect(
                host=pg.host,
                port=pg.port,
                user=pg.user,
                password=pg.password.get_secret_value() if pg.password else None,
                database=pg.database,
                timeout=timeout_s,
            )
        except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
            return system.DependencyState(state="down", detail=type(exc).__name__)
        try:
            version = await conn.fetchval("SHOW server_version")
        finally:
            await conn.close()
        return system.DependencyState(state="up", version=str(version))

    return probe


def create_app(
    config: TitanConfig | None = None,
    *,
    launch_token: str | None = None,
    probe: PostgresProbe | None = None,
) -> FastAPI:
    cfg = config if config is not None else load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("api_started", host=cfg.api.host, port=cfg.api.port)
        yield
        log.info("api_stopped")

    app = FastAPI(
        title="Project Titan API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.config = cfg
    app.state.launch_token = launch_token if launch_token is not None else launch_token_from_env()
    app.state.started_at = utc_now()
    app.state.probe_postgres = probe if probe is not None else postgres_probe(cfg.postgres)

    # The renderer runs on a different origin. Auth is the bearer token, never cookies.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.api.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
        max_age=600,
    )
    install_error_handlers(app)
    app.include_router(system.public, prefix=API_PREFIX)
    app.include_router(system.router, prefix=API_PREFIX)
    return app
