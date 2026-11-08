"""Database fixtures: each test gets a fresh, empty database on the configured server.

The server comes from the layered config (`TITAN__POSTGRES__HOST/PORT/USER/PASSWORD`). Tests are
skipped when it is unreachable, unless `TITAN_REQUIRE_POSTGRES=1` (CI) turns that into a failure.

Use from a `conftest.py`:

    from titan_testing.db import pg_server, temp_db  # noqa: F401
"""

from __future__ import annotations

import asyncio
import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import asyncpg
import pytest

from titan_core.config import PostgresConfig, load_config

REQUIRE_ENV = "TITAN_REQUIRE_POSTGRES"


def connect_kwargs(pg: PostgresConfig, database: str | None = None) -> dict[str, Any]:
    return {
        "host": pg.host,
        "port": pg.port,
        "user": pg.user,
        "password": pg.password.get_secret_value() if pg.password else None,
        "database": database or pg.database,
    }


@dataclass(frozen=True)
class TempDatabase:
    pg: PostgresConfig

    @property
    def url(self) -> str:
        return self.pg.sqlalchemy_url("asyncpg")

    async def connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(**connect_kwargs(self.pg))


async def _admin(pg: PostgresConfig, sql: str) -> None:
    conn = await asyncpg.connect(**connect_kwargs(pg, "postgres"), timeout=3)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def pg_server() -> PostgresConfig:
    pg = load_config(user_config=False).postgres
    try:
        asyncio.run(_admin(pg, "SELECT 1"))
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        if os.environ.get(REQUIRE_ENV) == "1":
            pytest.fail(f"PostgreSQL required but unreachable at {pg.host}:{pg.port}: {exc!r}")
        pytest.skip(f"PostgreSQL unreachable at {pg.host}:{pg.port} ({type(exc).__name__})")
    return pg


@pytest.fixture
def temp_db(pg_server: PostgresConfig) -> Iterator[TempDatabase]:
    name = f"titan_test_{secrets.token_hex(6)}"
    asyncio.run(_admin(pg_server, f'CREATE DATABASE "{name}"'))
    try:
        yield TempDatabase(pg_server.model_copy(update={"database": name}))
    finally:
        asyncio.run(_admin(pg_server, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
