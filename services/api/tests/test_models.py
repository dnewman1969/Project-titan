from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient

from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_core.protocol.system import DependencyState
from titan_models.fake import FakeProvider
from titan_models.registry import ModelsRegistry
from titan_models.routing import load_models_yaml

TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def models_client(tmp_path: Path) -> Iterator[TestClient]:
    primary = FakeProvider(id="ollama", models=["qwen3:8b", "qwen3:4b"])
    config = load_models_yaml()
    registry = ModelsRegistry(config=config, providers={"ollama": primary})
    app = create_app(
        TitanConfig(),
        launch_token=TOKEN,
        checks={"postgres": _postgres_up},
        supervisor=lambda: None,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        start_persister=False,
        enable_database=False,
        models_registry=registry,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


async def _postgres_up() -> DependencyState:
    return DependencyState(state="up", version="16")


def test_models_list(models_client: TestClient) -> None:
    response = models_client.get("/api/v1/models", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["providers"][0]["id"] == "ollama"
    assert body["providers"][0]["healthy"] is True


def test_models_routes(models_client: TestClient) -> None:
    response = models_client.get("/api/v1/models/routes", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "vram_12gb"
    assert "director" in body["roles"]


def test_models_pull_returns_job_id(models_client: TestClient) -> None:
    response = models_client.post(
        "/api/v1/models/pull",
        headers=AUTH,
        json={"provider": "ollama", "model": "qwen3:8b"},
    )
    assert response.status_code == 202
    assert "job_id" in response.json()


def test_models_routes_validation(models_client: TestClient) -> None:
    response = models_client.put(
        "/api/v1/models/routes",
        headers=AUTH,
        json={
            "profile": "vram_12gb",
            "roles": {"agent": {"provider": "ollama", "model": "nope:99"}},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
