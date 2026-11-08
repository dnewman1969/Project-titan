"""`/settings` GET and PATCH with versioning (M2.T3)."""

from __future__ import annotations

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient

from titan_api.auth import LAUNCH_TOKEN_ENV
from titan_api.errors import PROBLEM_JSON
from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_core.protocol.system import SupervisorStatus
from titan_db.migrate import upgrade
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase, pg_server  # noqa: F401

TOKEN = "settings-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def no_supervisor() -> SupervisorStatus | None:
    return None

pytestmark = pytest.mark.postgres


@pytest.fixture
def api_client(pg_server, temp_db: TempDatabase, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:  # noqa: F811
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, TOKEN)
    upgrade(temp_db.url)
    engine = create_engine(temp_db.pg)
    factory = create_session_factory(engine)
    app = create_app(
        TitanConfig(),
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        engine=engine,
        session_factory=factory,
        start_persister=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_settings_get_and_patch(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/settings", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["values"] == {}
    patch = api_client.patch(
        "/api/v1/settings",
        headers={**AUTH, "If-Match": "1"},
        json={"ui.layout": {"panels": ["game"]}, "floor": {"min_gap_ms": 1800}},
    )
    assert patch.status_code == 200
    updated = patch.json()
    assert updated["version"] == 2
    assert updated["values"]["ui.layout"]["panels"] == ["game"]
    mismatch = api_client.patch(
        "/api/v1/settings",
        headers={**AUTH, "If-Match": "1"},
        json={"floor": {"min_gap_ms": 1600}},
    )
    assert mismatch.status_code == 412
    assert mismatch.headers["content-type"] == PROBLEM_JSON
    assert mismatch.json()["code"] == "VERSION_MISMATCH"
