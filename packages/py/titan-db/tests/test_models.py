"""ORM metadata covers every table from the initial schema."""

from __future__ import annotations

from titan_db import migrate
from titan_db.models import Base
from titan_db.sql import created_tables

DDL_FILE = migrate.MIGRATIONS_DIR / "versions" / "0001_initial_schema.sql"
EXPECTED_TABLES = set(created_tables(DDL_FILE.read_text(encoding="utf-8")))


def test_metadata_tables_match_initial_schema() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES
