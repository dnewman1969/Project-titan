"""Initial schema: every table in Section 4.2.

The DDL lives verbatim in `0001_initial_schema.sql`, copied from the spec's Section 4.2 code
block; a test fails if the two drift. This migration adds what the spec describes in prose:
the `lg` schema for LangGraph checkpoints (Section 4.1) and the `set_updated_at()` trigger on
every table that has an `updated_at` column.

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from alembic import op

from titan_db.sql import created_tables, split_statements

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = (Path(__file__).with_suffix(".sql")).read_text(encoding="utf-8")

UPDATED_AT_TABLES = (
    "games",
    "game_profiles",
    "agent_personas",
    "agent_teams",
    "agents",
    "sessions",
    "missions",
    "tasks",
    "knowledge_entries",
    "strategies",
    "risk_entries",
    "control_bindings",
    "recordings",
    "video_projects",
    "upload_jobs",
    "settings",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS lg")
    for statement in split_statements(DDL):
        op.execute(statement)
    for table in UPDATED_AT_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS blackboard_current")
    for table in reversed(created_tables(DDL)):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP SCHEMA IF EXISTS lg CASCADE")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
