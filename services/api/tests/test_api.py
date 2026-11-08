from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from titan_api.auth import LAUNCH_TOKEN_ENV, launch_token_from_env
from titan_api.errors import PROBLEM_JSON
from titan_api.main import create_app, postgres_probe
from titan_api.routers.system import DependencyState
from titan_core.config import PostgresConfig, TitanConfig
from titan_core.errors import ErrorCode, TitanError

TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def fake_probe() -> DependencyState:
    return DependencyState(state="up", version="16.15")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(TitanConfig(), launch_token=TOKEN, probe=fake_probe)

    extra = APIRouter()

    @extra.get("/api/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    @extra.get("/api/v1/_ollama")
    async def ollama_down() -> None:
        raise TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Ollama is not running.", dependency="ollama")

    @extra.get("/api/v1/_items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    app.include_router(extra)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_health_is_unauthenticated(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_requires_bearer(client: TestClient) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["www-authenticate"] == "Bearer"
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["type"] == "https://titan.local/errors/unauthorized"
    assert body["instance"] == "/api/v1/system/status"
    wrong = client.get("/api/v1/system/status", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Invalid bearer token."


def test_status_with_token(client: TestClient) -> None:
    response = client.get("/api/v1/system/status", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["resource_guard_level"] == "L0"
    assert body["services"][0]["name"] == "api"
    assert body["services"][0]["state"] == "up"
    assert body["dependencies"]["postgres"] == {"state": "up", "version": "16.15", "detail": None}


def test_not_found_is_problem_json(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "NOT_FOUND"


def test_validation_errors(client: TestClient) -> None:
    response = client.get("/api/v1/_items/abc")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["errors"][0]["field"] == "path.item_id"


def test_titan_error_carries_dependency(client: TestClient) -> None:
    response = client.get("/api/v1/_ollama")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "DEPENDENCY_UNAVAILABLE"
    assert body["dependency"] == "ollama"


def test_unhandled_errors_are_internal(client: TestClient) -> None:
    response = client.get("/api/v1/_boom")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL"
    assert "kaboom" not in response.text


def test_openapi_is_served_under_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/openapi.json").json()["info"]["title"] == "Project Titan API"


def test_launch_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, "from-env")
    assert launch_token_from_env() == "from-env"
    monkeypatch.delenv(LAUNCH_TOKEN_ENV)
    generated = launch_token_from_env()
    assert len(generated) >= 32
    assert generated != launch_token_from_env()


async def test_postgres_probe_reports_down_on_closed_port() -> None:
    state = await postgres_probe(PostgresConfig(host="127.0.0.1", port=1), timeout_s=0.5)()
    assert state.state == "down"
    assert state.detail


def test_cors_preflight_allows_the_renderer_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/system/status",
        headers={
            "Origin": "app://titan",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "app://titan"
    assert "access-control-allow-credentials" not in response.headers
    get = client.get("/api/v1/system/status", headers={**AUTH, "Origin": "app://titan"})
    assert get.headers["access-control-allow-origin"] == "app://titan"


def test_cors_rejects_other_origins(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    get = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in get.headers


def test_cors_origins_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN__API__CORS_ORIGINS", '["app://titan", "http://localhost:5173"]')
    app = create_app(TitanConfig(), launch_token=TOKEN, probe=fake_probe)
    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
