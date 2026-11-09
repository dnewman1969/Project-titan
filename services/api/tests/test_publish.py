"""YouTube publish stub API."""

from __future__ import annotations

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from titan_api.auth import LAUNCH_TOKEN_ENV
from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_core.protocol.system import SupervisorStatus
from titan_db.models.games import Game
from titan_db.seed import seed_all
from titan_db.session import create_session_factory
from titan_testing.db import TempDatabase

TOKEN = "publish-token"
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


@pytest.fixture
def game_slug(migrated_db: TempDatabase) -> str:
    import asyncio

    from titan_db.session import create_engine

    async def _load() -> str:
        engine = create_engine(migrated_db.pg)
        factory = create_session_factory(engine)
        await seed_all(factory)
        async with factory() as session:
            slug = await session.scalar(select(Game.slug).limit(1))
        await engine.dispose()
        assert slug is not None
        return slug

    return asyncio.run(_load())


def test_youtube_stub_auth_and_draft_upload(api_client: TestClient, game_slug: str) -> None:
    empty = api_client.get("/api/v1/accounts/youtube", headers=AUTH)
    assert empty.status_code == 200
    assert empty.json()["connected"] is False

    blocked = api_client.post(
        "/api/v1/upload-jobs",
        headers=AUTH,
        json={"title": "No auth"},
    )
    assert blocked.status_code == 409

    connected = api_client.post("/api/v1/accounts/youtube/connect", headers=AUTH)
    assert connected.status_code == 200, connected.text
    assert connected.json()["connected"] is True
    assert connected.json()["account"]["remote_channel_id"] == "stub-channel"

    status = api_client.get("/api/v1/accounts/youtube", headers=AUTH)
    assert status.json()["connected"] is True

    created = api_client.post(
        "/api/v1/sessions",
        headers=AUTH,
        json={"game_slug": game_slug, "title": "publish sess", "settings": {"agents_enabled": False}},
    )
    assert created.status_code == 201
    sid = created.json()["id"]

    draft = api_client.post(
        "/api/v1/upload-jobs",
        headers=AUTH,
        json={"title": "Beta draft", "session_id": sid, "privacy": "private"},
    )
    assert draft.status_code == 201, draft.text
    job = draft.json()
    assert job["status"] == "awaiting_approval"
    assert job["privacy"] == "private"
    assert job["metadata"]["stub"] is True
    job_id = job["id"]

    listed = api_client.get("/api/v1/upload-jobs", headers=AUTH)
    assert listed.status_code == 200
    assert any(item["id"] == job_id for item in listed.json()["items"])

    too_soon = api_client.post(f"/api/v1/upload-jobs/{job_id}/upload", headers=AUTH)
    assert too_soon.status_code == 409

    approved = api_client.post(f"/api/v1/upload-jobs/{job_id}/approve", headers=AUTH)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"]

    uploaded = api_client.post(f"/api/v1/upload-jobs/{job_id}/upload", headers=AUTH)
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["status"] == "published"
    assert body["remote_video_id"]
    assert "studio.youtube.com" in body["remote_url"]

    again = api_client.post("/api/v1/accounts/youtube/connect", headers=AUTH)
    assert again.status_code == 200
    assert again.json()["account"]["id"] == connected.json()["account"]["id"]

    disconnected = api_client.post("/api/v1/accounts/youtube/disconnect", headers=AUTH)
    assert disconnected.status_code == 200
    assert disconnected.json()["connected"] is False

    # Second disconnect is a no-op once revoked (account still present, not connected).
    again_disc = api_client.post("/api/v1/accounts/youtube/disconnect", headers=AUTH)
    assert again_disc.status_code == 200
    assert again_disc.json()["connected"] is False


def test_youtube_stub_error_paths(api_client: TestClient) -> None:
    missing = api_client.post("/api/v1/accounts/youtube/disconnect", headers=AUTH)
    assert missing.status_code == 200
    assert missing.json()["account"] is None

    api_client.post("/api/v1/accounts/youtube/connect", headers=AUTH)
    bad_session = api_client.post(
        "/api/v1/upload-jobs",
        headers=AUTH,
        json={"title": "Missing session", "session_id": "00000000-0000-4000-8000-000000000099"},
    )
    assert bad_session.status_code == 404

    draft = api_client.post(
        "/api/v1/upload-jobs",
        headers=AUTH,
        json={"title": "Standalone draft", "privacy": "unlisted"},
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["privacy"] == "unlisted"
    job_id = draft.json()["id"]

    approved = api_client.post(f"/api/v1/upload-jobs/{job_id}/approve", headers=AUTH)
    assert approved.status_code == 200
    # Re-approve after approved should conflict.
    again = api_client.post(f"/api/v1/upload-jobs/{job_id}/approve", headers=AUTH)
    assert again.status_code == 409

    missing_job = api_client.post(
        "/api/v1/upload-jobs/00000000-0000-4000-8000-000000000088/approve",
        headers=AUTH,
    )
    assert missing_job.status_code == 404

    missing_upload = api_client.post(
        "/api/v1/upload-jobs/00000000-0000-4000-8000-000000000088/upload",
        headers=AUTH,
    )
    assert missing_upload.status_code == 404

    uploaded = api_client.post(f"/api/v1/upload-jobs/{job_id}/upload", headers=AUTH)
    assert uploaded.status_code == 200
    assert uploaded.json()["status"] == "published"
