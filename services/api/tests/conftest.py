"""Shared DB fixtures for API integration tests."""

from __future__ import annotations

import pytest

from titan_db.migrate import upgrade
from titan_testing.db import pg_server, temp_db

__all__ = ["migrated_db", "pg_server", "temp_db"]


@pytest.fixture
def migrated_db(temp_db):
    """Empty database with Alembic at head (same as CI `test-py-linux`)."""
    upgrade(temp_db.url)
    return temp_db
