"""Games API routes (M4.T5)."""

from __future__ import annotations

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient

from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_testing.db import TempDatabase

TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.postgres


@pytest.fixture
def games_client(migrated_db: TempDatabase) -> Iterator[TestClient]:
    cfg = TitanConfig().model_copy(update={"postgres": migrated_db.pg})
    app = create_app(
        cfg,
        launch_token=TOKEN,
        checks={},
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        start_persister=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_list_games_syncs_from_entry_points(games_client: TestClient) -> None:
    response = games_client.get("/api/v1/games", headers=AUTH)
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()["items"]}
    assert {"ksp", "ets2", "ats"}.issubset(slugs)


def test_list_games_can_include_profiles(games_client: TestClient) -> None:
    response = games_client.get("/api/v1/games?include_profiles=true", headers=AUTH)
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert "profiles" in items[0]
