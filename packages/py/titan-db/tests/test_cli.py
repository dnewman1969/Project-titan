from __future__ import annotations

import pytest

from titan_db import cli, migrate


def test_cli_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(migrate, "upgrade", lambda url, rev: calls.append(("up", url, rev)))
    monkeypatch.setattr(migrate, "downgrade", lambda url, rev: calls.append(("down", url, rev)))
    assert cli.main(["upgrade"]) == 0
    assert cli.main(["downgrade", "0001"]) == 0
    assert [(c[0], c[2]) for c in calls] == [("up", "head"), ("down", "0001")]
    assert calls[0][1].startswith("postgresql+asyncpg://")


def test_alembic_config_escapes_percent() -> None:
    cfg = migrate.alembic_config("postgresql+asyncpg://u:p%40ss@h/db")
    assert cfg.get_main_option("sqlalchemy.url") == "postgresql+asyncpg://u:p%40ss@h/db"
    assert cfg.get_main_option("script_location") == str(migrate.MIGRATIONS_DIR)
