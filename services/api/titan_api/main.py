"""App factory, routers, middleware and lifespan (Section 3, `services/api/titan_api/main.py`)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from titan_api import API_PREFIX
from titan_api.auth import launch_token_from_env
from titan_api.errors import install_error_handlers
from titan_api.persister import StreamPersister
from titan_api.routers import safety, settings, system
from titan_api.safety import SafetyController
from titan_api.supervisor_client import SupervisorProbe, supervisor_probe
from titan_api.ws import router as ws_router
from titan_core.clock import utc_now
from titan_core.config import PostgresConfig, TitanConfig, load_config
from titan_core.health import Check, check_chroma, check_obs, check_ollama, check_postgres, check_redis
from titan_core.logging import get_logger
from titan_core.protocol.system import DependencyState
from titan_core.streams import redis_client
from titan_db.session import create_engine, create_session_factory

log = get_logger(__name__)


def postgres_probe(pg: PostgresConfig, timeout_s: float = 1.0) -> Check:
    """A coroutine function that reports whether Postgres accepts connections."""

    async def probe() -> DependencyState:
        return await check_postgres(pg, timeout_s=timeout_s)

    return probe


def dependency_checks(cfg: TitanConfig) -> dict[str, Check]:
    """The `dependencies` of `/system/status` (Section 5.2)."""

    async def postgres() -> DependencyState:
        return await check_postgres(cfg.postgres)

    async def redis() -> DependencyState:
        return await check_redis(cfg.redis)

    async def chroma() -> DependencyState:
        return await check_chroma(cfg.chroma)

    return {"postgres": postgres, "redis": redis, "chroma": chroma, "ollama": check_ollama, "obs": check_obs}


def create_app(
    config: TitanConfig | None = None,
    *,
    launch_token: str | None = None,
    checks: Mapping[str, Check] | None = None,
    supervisor: SupervisorProbe | None = None,
    redis: aioredis.Redis | None = None,
    engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    start_persister: bool = True,
) -> FastAPI:
    cfg = config if config is not None else load_config()
    token = launch_token if launch_token is not None else launch_token_from_env()
    client = redis if redis is not None else redis_client(cfg.redis)
    controller = SafetyController(client)

    owns_engine = engine is None
    db_engine = engine if engine is not None else create_engine(cfg.postgres)
    session_maker = session_factory if session_factory is not None else create_session_factory(db_engine)
    persister = StreamPersister(client, session_maker) if start_persister else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await controller.load()
        if persister is not None:
            await persister.start()
        log.info("api_started", host=cfg.api.host, port=cfg.api.port)
        yield
        if persister is not None:
            await persister.stop()
        await controller.drain()
        if owns_engine:
            await db_engine.dispose()
        if redis is None:
            await client.aclose()
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
    app.state.launch_token = token
    app.state.started_at = utc_now()
    app.state.dependency_checks = dict(checks) if checks is not None else dependency_checks(cfg)
    app.state.probe_supervisor = (
        supervisor if supervisor is not None else supervisor_probe(cfg.supervisor, token)
    )
    app.state.redis = client
    app.state.safety = controller
    app.state.engine = db_engine
    app.state.session_factory = session_maker
    app.state.persister = persister

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
    app.include_router(safety.router, prefix=API_PREFIX)
    app.include_router(settings.router, prefix=API_PREFIX)
    app.include_router(ws_router, prefix=API_PREFIX)
    return app
