"""Settings repository and optimistic versioning."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_core.errors import ErrorCode, TitanError
from titan_db.repositories.settings import SettingsRepository
from titan_db.session import create_engine, create_session_factory
from titan_testing.db import TempDatabase

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def db_factory(migrated_db: TempDatabase) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(migrated_db.pg)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


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
