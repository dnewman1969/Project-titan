from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from titan_supervisor.core import Supervisor
from titan_supervisor.metrics import MetricsSampler, NvmlSampler, PresentMonTracker
from titan_supervisor.server import bind, create_app

from .fakes import FAST, FakeProcess, fast_policy

TOKEN = "launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def parts() -> Iterator[tuple[TestClient, list[str], MetricsSampler]]:
    shutdowns: list[str] = []
    supervisor = Supervisor([FakeProcess("api")], timing=FAST, policy_factory=fast_policy)
    sampler = MetricsSampler(PresentMonTracker(None), NvmlSampler(enabled=False))
    app = create_app(supervisor, token=TOKEN, sampler=sampler, on_shutdown=lambda: shutdowns.append("x"))
    with TestClient(app) as client:
        yield client, shutdowns, sampler


def test_health_is_open_and_everything_else_needs_the_token(
    parts: tuple[TestClient, list[str], MetricsSampler],
) -> None:
    client, _, _ = parts
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/shutdown").status_code == 401


def test_status_and_events_since(parts: tuple[TestClient, list[str], MetricsSampler]) -> None:
    client, _, _ = parts
    body = client.get("/status", headers=AUTH).json()
    assert body["ready"] is False
    assert body["services"][0]["name"] == "api"
    assert body["services"][0]["state"] == "unknown"
    assert client.get("/status?since=5", headers=AUTH).json()["events"] == []


def test_restart_unknown_process_is_404(parts: tuple[TestClient, list[str], MetricsSampler]) -> None:
    client, _, _ = parts
    assert client.post("/processes/nope/restart", headers=AUTH).status_code == 404
    assert client.post("/processes/api/restart", headers=AUTH).status_code == 202


def test_metrics_and_game_target(parts: tuple[TestClient, list[str], MetricsSampler]) -> None:
    client, _, sampler = parts
    assert client.get("/metrics/latest", headers=AUTH).status_code == 404
    sampler.latest = sampler.sample()
    body = client.get("/metrics/latest", headers=AUTH).json()
    assert body["game_fps"] is None
    assert client.put("/metrics/game", json={"pid": 1234}, headers=AUTH).json() == {"pid": 1234}
    assert sampler.presentmon.pid == 1234
    assert client.put("/metrics/game", json={"pid": 0}, headers=AUTH).status_code == 422
    assert client.put("/metrics/game", json={"pid": None}, headers=AUTH).status_code == 200


def test_shutdown_calls_back(parts: tuple[TestClient, list[str], MetricsSampler]) -> None:
    client, shutdowns, _ = parts
    assert client.post("/shutdown", headers=AUTH).status_code == 202
    assert shutdowns == ["x"]


def test_bind_fails_fast_when_the_port_is_taken() -> None:
    first = bind("127.0.0.1", 0)
    port = first.getsockname()[1]
    try:
        with pytest.raises(OSError):
            bind("127.0.0.1", port)
    finally:
        first.close()
