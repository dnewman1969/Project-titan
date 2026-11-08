from __future__ import annotations

from pathlib import Path

from titan_core.config import TitanConfig
from titan_supervisor.catalog import ChildEnv, build_units, chroma_command
from titan_supervisor.postgres import PostgresUnit
from titan_supervisor.units import ChildUnit, ExternalUnit, OneShotUnit


def config(**sections: object) -> TitanConfig:
    return TitanConfig.model_validate(sections)


def test_default_process_table_follows_the_start_order(tmp_path: Path) -> None:
    cfg = config(chroma={"data_dir": str(tmp_path / "chroma"), "command": ["chroma"]})
    units = build_units(cfg, app_dir=None)
    assert [u.name for u in units] == ["postgres", "redis", "chroma", "migrate", "api"]
    assert isinstance(units[0], PostgresUnit)
    assert isinstance(units[1], ExternalUnit)
    assert isinstance(units[3], OneShotUnit)
    assert units[3].requires == ("postgres",)
    chroma = units[2]
    assert isinstance(chroma, ChildUnit)
    assert chroma.argv() == [
        "chroma", "run", "--host", "127.0.0.1", "--port", "8766", "--path", str(tmp_path / "chroma"),
    ]  # fmt: skip


def test_external_modes_and_subset() -> None:
    cfg = config(
        postgres={"mode": "external"},
        chroma={"mode": "external"},
        supervisor={"processes": ["postgres", "chroma", "api"]},
    )
    units = build_units(cfg, app_dir=None)
    assert [type(u).__name__ for u in units] == ["ExternalUnit", "ExternalUnit", "ChildUnit"]


def test_migrate_without_managed_postgres_has_no_requirement() -> None:
    units = build_units(config(supervisor={"processes": ["migrate"]}), app_dir=None)
    assert units[0].requires == ()


def test_child_env_carries_secrets_only_in_the_environment() -> None:
    cfg = config(postgres={"password": "pg-secret"}, redis={"password": "redis-secret"})
    env = ChildEnv(cfg, base={"PATH": "/bin"})
    values = env()
    assert values["TITAN__POSTGRES__PASSWORD"] == "pg-secret"
    assert values["TITAN__REDIS__PASSWORD"] == "redis-secret"
    assert values["PYTHONUNBUFFERED"] == "1"
    env.postgres_password = "generated"
    assert env()["TITAN__POSTGRES__PASSWORD"] == "generated"
    api = build_units(cfg, app_dir=None, env=env)[-1]
    assert isinstance(api, ChildUnit)
    assert "pg-secret" not in " ".join(api.argv())


def test_chroma_command_prefers_config() -> None:
    assert chroma_command(["/opt/chroma"]) == ["/opt/chroma"]
    command = chroma_command(None)
    assert command[-1].startswith("chroma") or command[-1].endswith(("chroma", "chroma.exe"))
