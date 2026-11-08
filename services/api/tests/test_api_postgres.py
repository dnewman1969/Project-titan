from __future__ import annotations

import pytest

from titan_api.main import postgres_probe
from titan_core.config import PostgresConfig
from titan_testing.db import pg_server  # noqa: F401


@pytest.mark.postgres
async def test_postgres_probe_reports_up(pg_server: PostgresConfig) -> None:  # noqa: F811
    state = await postgres_probe(pg_server.model_copy(update={"database": "postgres"}))()
    assert state.state == "up"
    assert state.version is not None
    assert state.version.startswith("16")
