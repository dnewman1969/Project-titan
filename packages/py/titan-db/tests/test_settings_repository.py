"""Settings repository and optimistic versioning."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_core.errors import ErrorCode, TitanError
from titan_db.migrate import upgrade
from titan_db.repositories.settings import SettingsRepository
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase, pg_server  # noqa: F401

pytestmark = pytest.mark.postgres


@pytest.fixture
def db_factory(pg_server, temp_db: TempDatabase) -> async_sessionmaker[AsyncSession]:  # noqa: F811
    upgrade(temp_db.url)
    engine = create_engine(temp_db.pg)
    return create_session_factory(engine)


@pytest.mark.asyncio
async def test_settings_versioning_and_merge(db_factory: async_sessionmaker[AsyncSession]) -> None:
    async with db_factory() as session:
        repo = SettingsRepository(session)
        base = await repo.get()
        assert base.version == 1
        assert base.values == {}
        updated = await repo.patch({"floor": {"min_gap_ms": 2200}}, expected_version=1)
        assert updated.version == 2
        assert updated.values["floor"]["min_gap_ms"] == 2200
        with pytest.raises(TitanError) as exc:
            await repo.patch({"floor": {"max_words": 25}}, expected_version=1)
        assert exc.value.code is ErrorCode.VERSION_MISMATCH
        overrides = await repo.titan_overrides()
        assert overrides["floor"]["min_gap_ms"] == 2200
