"""Direct unit coverage for youtube_stub helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from titan_api.youtube_stub import (
    account_json,
    approve_upload,
    connect_stub_account,
    create_draft_upload,
    disconnect_stub_account,
    get_youtube_account,
    list_upload_jobs,
    run_stub_upload,
    upload_json,
)
from titan_core.clock import utc_now
from titan_core.errors import TitanError
from titan_core.ids import uuid7
from titan_db.models.games import Game
from titan_db.models.publishing import PlatformAccount
from titan_db.models.recording import Recording
from titan_db.models.sessions import Session
from titan_db.seed import seed_all
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase

pytestmark = pytest.mark.postgres


def test_youtube_stub_helpers_cover_paths(migrated_db: TempDatabase, tmp_path: Path) -> None:
    data_dir = tmp_path / "session"
    rec_dir = data_dir / "recording"
    rec_dir.mkdir(parents=True)

    async def _run() -> None:
        engine = create_engine(migrated_db.pg)
        factory = create_session_factory(engine)
        await seed_all(factory)
        async with factory() as db:
            assert await get_youtube_account(db) is None
            assert await disconnect_stub_account(db) is None

            first = await connect_stub_account(db)
            assert first.status == "connected"
            assert account_json(first)["stub"] is True
            second = await connect_stub_account(db)
            assert second.id == first.id

            with pytest.raises(TitanError):
                await create_draft_upload(db, title="x", session_id=uuid7())

            game_id = await db.scalar(select(Game.id).limit(1))
            assert game_id is not None
            session = Session(
                id=uuid7(),
                game_id=game_id,
                title="unit",
                mode="observe",
                state="live",
                data_dir=str(data_dir),
                settings={},
            )
            db.add(session)
            await db.flush()
            rec = Recording(
                id=uuid7(),
                session_id=session.id,
                state="complete",
                preset={},
                root_dir=str(rec_dir),
                manifest_path=str(rec_dir / "manifest.json"),
                started_at=utc_now(),
            )
            db.add(rec)
            await db.flush()

            job, project = await create_draft_upload(
                db,
                title="Unit draft",
                session_id=session.id,
                privacy="private",
            )
            assert job.status == "awaiting_approval"
            assert project.output_path == str(rec_dir)
            listed = await list_upload_jobs(db, limit=5)
            assert any(j.id == job.id for j, _ in listed)
            assert upload_json(job, project=project)["title"] == "Unit draft"

            with pytest.raises(TitanError):
                await run_stub_upload(db, job.id)

            approved = await approve_upload(db, job.id)
            assert approved.status == "approved"
            with pytest.raises(TitanError):
                await approve_upload(db, job.id)

            published = await run_stub_upload(db, job.id)
            assert published.status == "published"
            assert published.remote_video_id

            with pytest.raises(TitanError):
                await approve_upload(db, uuid7())
            with pytest.raises(TitanError):
                await run_stub_upload(db, uuid7())

            revoked = await disconnect_stub_account(db)
            assert revoked is not None
            assert revoked.status == "revoked"
            with pytest.raises(TitanError):
                await create_draft_upload(db, title="blocked", session_id=None)
            assert isinstance(await db.scalar(select(PlatformAccount).limit(1)), PlatformAccount)
            await db.commit()
        await engine.dispose()

    asyncio.run(_run())
