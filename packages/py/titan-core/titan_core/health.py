"""Dependency health checks shared by the supervisor and the API (Sections 2.3 and 5.2).

Every check returns a `DependencyState` and never raises for an unreachable or broken service.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

import asyncpg
import redis.asyncio as aioredis
import redis.exceptions

from titan_core.config import ChromaConfig, PostgresConfig, RedisConfig
from titan_core.http import HTTPError, local_client
from titan_core.protocol.system import DependencyState
from titan_core.secrets import resolve_secret
from titan_core.streams import REDIS_PROTOCOL

Check = Callable[[], Awaitable[DependencyState]]

OLLAMA_URL = "http://127.0.0.1:11434"
OBS_WEBSOCKET = ("127.0.0.1", 4455)


def _down(exc: BaseException | str) -> DependencyState:
    return DependencyState(state="down", detail=exc if isinstance(exc, str) else type(exc).__name__)


async def check_postgres(
    pg: PostgresConfig, *, database: str | None = None, timeout_s: float = 1.0
) -> DependencyState:
    password = resolve_secret(pg.password, "postgres")
    try:
        conn = await asyncpg.connect(
            host=pg.host,
            port=pg.port,
            user=pg.user,
            password=password.get_secret_value() if password else None,
            database=database or pg.database,
            timeout=timeout_s,
        )
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        return _down(exc)
    try:
        version = await conn.fetchval("SHOW server_version")
    finally:
        await conn.close()
    return DependencyState(state="up", version=str(version))


async def check_redis(cfg: RedisConfig, *, timeout_s: float = 1.0) -> DependencyState:
    """Up when an authenticated INFO works. Degraded when the server accepts clients without a
    password, because Titan requires `requirepass` (M1.T2)."""
    password = resolve_secret(cfg.password, "redis")
    client = aioredis.Redis.from_url(
        cfg.url,
        password=password.get_secret_value() if password else None,
        socket_timeout=timeout_s,
        socket_connect_timeout=timeout_s,
        decode_responses=True,
        protocol=REDIS_PROTOCOL,
    )
    try:
        info = await client.info("server")
    except redis.exceptions.AuthenticationError:
        return _down("authentication failed: set the password in the keyring as titan/redis")
    except (redis.exceptions.RedisError, OSError) as exc:
        return _down(exc)
    finally:
        await client.aclose()
    version = str(info.get("redis_version", "")) or None
    anonymous = aioredis.Redis.from_url(
        cfg.url, socket_timeout=timeout_s, socket_connect_timeout=timeout_s, protocol=REDIS_PROTOCOL
    )
    try:
        await anonymous.ping()
    except (redis.exceptions.RedisError, OSError):
        return DependencyState(state="up", version=version)
    finally:
        await anonymous.aclose()
    return DependencyState(state="degraded", version=version, detail="requirepass is not set")


async def check_http(url: str, *, timeout_s: float = 1.0, version_key: str | None = None) -> DependencyState:
    """Up on HTTP 200. `version_key` reads the version from a JSON response body."""
    try:
        async with local_client(timeout_s=timeout_s) as client:
            response = await client.get(url)
    except HTTPError as exc:
        return _down(exc)
    if response.status_code != 200:
        return DependencyState(state="degraded", detail=f"HTTP {response.status_code}")
    version: str | None = None
    if version_key is not None:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get(version_key) is not None:
            version = str(body[version_key])
    return DependencyState(state="up", version=version)


async def check_chroma(cfg: ChromaConfig, *, timeout_s: float = 1.0) -> DependencyState:
    state = await check_http(f"{cfg.url}/api/v2/heartbeat", timeout_s=timeout_s)
    if state.state != "up":
        return state
    try:
        async with local_client(timeout_s=timeout_s) as client:
            response = await client.get(f"{cfg.url}/api/v2/version")
        version = response.json() if response.status_code == 200 else None
    except (HTTPError, ValueError):
        version = None
    return DependencyState(state="up", version=str(version) if isinstance(version, str) else None)


async def check_ollama(url: str = OLLAMA_URL, *, timeout_s: float = 1.0) -> DependencyState:
    return await check_http(f"{url}/api/version", timeout_s=timeout_s, version_key="version")


async def check_tcp(host: str, port: int, *, timeout_s: float = 1.0) -> DependencyState:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_s)
    except (OSError, TimeoutError) as exc:
        return _down(exc)
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return DependencyState(state="up")


async def check_obs(
    host: str = OBS_WEBSOCKET[0],
    port: int = OBS_WEBSOCKET[1],
    *,
    timeout_s: float = 1.0,
) -> DependencyState:
    """obs-websocket TCP reachability; Ops Center /capture/obs does the v5 handshake."""
    return await check_tcp(host, port, timeout_s=timeout_s)


async def timed(check: Check, timeout_s: float) -> DependencyState:
    """Run `check`, reporting `down` (detail `timeout`) if it overruns `timeout_s`."""
    start = time.monotonic()
    try:
        return await asyncio.wait_for(check(), timeout_s)
    except TimeoutError:
        return _down(f"timeout after {time.monotonic() - start:.1f}s")
