"""Programmatic Alembic entry points (used by the supervisor start order, the CLI and tests)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from titan_core.config import PostgresConfig

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str) -> Config:
    """Alembic config pointing at the packaged migrations and the given SQLAlchemy URL."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def database_url(pg: PostgresConfig) -> str:
    return pg.sqlalchemy_url("asyncpg")


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)
