from __future__ import annotations

import fakeredis
import pytest

from titan_db.migrate import upgrade
from titan_testing.db import TempDatabase, pg_server, temp_db  # noqa: F401


@pytest.fixture
def fake_redis():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def migrated_db(temp_db: TempDatabase) -> TempDatabase:  # noqa: F811
    upgrade(temp_db.url)
    return temp_db
