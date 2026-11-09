"""Capture / OBS probe routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from titan_api.auth import LAUNCH_TOKEN_ENV
from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_core.health import DependencyState
from titan_core.obs_ws import ObsRecordStatus
from titan_core.protocol.system import SupervisorStatus
from titan_testing.db import TempDatabase

TOKEN = "capture-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.postgres


async def no_supervisor() -> SupervisorStatus | None:
    return None


@pytest.fixture
def api_client(migrated_db: TempDatabase, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, TOKEN)
    cfg = TitanConfig().model_copy(update={"postgres": migrated_db.pg})
    app = create_app(
        cfg,
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        start_persister=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_obs_capture_down(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _down(*_args: Any, **_kwargs: Any) -> DependencyState:
        return DependencyState(state="down", detail="refused")

    monkeypatch.setattr("titan_api.routers.capture.check_obs", _down)
    res = api_client.get("/api/v1/capture/obs", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "down"
    assert body["connected"] is False


def test_obs_capture_connected(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _up(*_args: Any, **_kwargs: Any) -> DependencyState:
        return DependencyState(state="up")

    class _FakeObs:
        host = "127.0.0.1"
        port = 4455
        timeout_s = 5.0

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def get_version(self) -> dict[str, Any]:
            return {"obsVersion": "30.1.0"}

        async def provision_titan_profile(self) -> dict[str, str]:
            return {
                "profile": "Titan",
                "collection": "Titan",
                "scene": "Titan Gameplay",
                "status": "planned",
                "obs_version": "30.1.0",
            }

        async def get_record_status(self) -> ObsRecordStatus:
            return ObsRecordStatus(active=True, paused=False, duration_ms=1500)

    monkeypatch.setattr("titan_api.routers.capture.check_obs", _up)
    monkeypatch.setattr("titan_api.routers.capture.make_obs_client", lambda: _FakeObs())
    res = api_client.get("/api/v1/capture/obs", headers=AUTH)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"] == "up"
    assert body["connected"] is True
    assert body["version"]["obsVersion"] == "30.1.0"
    assert body["provision"]["status"] == "planned"
    assert body["record"]["active"] is True
    assert body["record"]["duration_ms"] == 1500


def test_obs_capture_handshake_degraded(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _up(*_args: Any, **_kwargs: Any) -> DependencyState:
        return DependencyState(state="up")

    class _BadObs:
        host = "127.0.0.1"
        port = 4455
        timeout_s = 5.0

        async def connect(self) -> None:
            msg = "handshake failed"
            raise RuntimeError(msg)

        async def close(self) -> None:
            return None

    monkeypatch.setattr("titan_api.routers.capture.check_obs", _up)
    monkeypatch.setattr("titan_api.routers.capture.make_obs_client", lambda: _BadObs())
    res = api_client.get("/api/v1/capture/obs", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "degraded"
    assert body["connected"] is False
    assert "handshake" in (body.get("detail") or "")
