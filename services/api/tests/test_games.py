"""Games API routes (M4.T5)."""

from __future__ import annotations

import os
import site
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import fakeredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_api.main import create_app
from titan_core.config import TitanConfig
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase

REPO = Path(__file__).resolve().parents[3]
TOKEN = "test-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def db_factory(migrated_db: TempDatabase) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(migrated_db.pg)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def _client(factory: async_sessionmaker[AsyncSession]) -> TestClient:
    app = create_app(
        TitanConfig().model_copy(update={"postgres": factory.kw.get("bind", None)}),  # type: ignore[arg-type]
        launch_token=TOKEN,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        session_factory=factory,
        start_persister=False,
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def games_client(migrated_db: TempDatabase, db_factory: async_sessionmaker[AsyncSession]) -> Iterator[TestClient]:
    cfg = TitanConfig().model_copy(update={"postgres": migrated_db.pg})
    app = create_app(
        cfg,
        launch_token=TOKEN,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        session_factory=db_factory,
        start_persister=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_list_games_syncs_from_entry_points(games_client: TestClient) -> None:
    response = games_client.get("/api/v1/games", headers=AUTH)
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()["items"]}
    assert {"ksp", "ets2", "ats"}.issubset(slugs)


def test_install_testgame_into_temp_target_surfaces_in_games(
    migrated_db: TempDatabase,
    db_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    site_dir = tmp_path / "site-packages"
    site_dir.mkdir()
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--target",
            str(site_dir),
            str(REPO / "packages" / "py" / "titan-sdk-games"),
            str(REPO / "packages" / "py" / "titan-core"),
            str(REPO / "games" / "_testgame"),
        ],
        check=True,
        cwd=REPO,
    )
    env = {**os.environ, "PYTHONPATH": str(site_dir)}
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "from titan_sdk_games.loader import load_adapters; print('testgame' in load_adapters())",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
    )
    assert probe.stdout.strip() == "True"

    site.addsitedir(str(site_dir))
    cfg = TitanConfig().model_copy(update={"postgres": migrated_db.pg})
    app = create_app(
        cfg,
        launch_token=TOKEN,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        session_factory=db_factory,
        start_persister=False,
    )
    app.state.game_catalog.reload()
    with TestClient(app) as client:
        response = client.get("/api/v1/games", headers=AUTH)
        assert response.status_code == 200
        slugs = {item["slug"] for item in response.json()["items"]}
        assert "testgame" in slugs
