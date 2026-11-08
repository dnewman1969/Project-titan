"""Config layering (Section 9.5): app yaml < user yaml < settings table < env < CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from titan_core import config as cfg_mod
from titan_core.config import TitanConfig, deep_merge, expand_path, find_app_config_dir, load_config

REPO_CONFIG = Path(__file__).resolve().parents[4] / "config"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in list(os.environ):
        if key.upper().startswith("TITAN__") or key == cfg_mod.CONFIG_DIR_ENV:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def app_dir(tmp_path: Path) -> Path:
    d = tmp_path / "app" / "config"
    d.mkdir(parents=True)
    (d / "titan.yaml").write_text(
        "api: { host: 127.0.0.1, port: 8765 }\n"
        "postgres: { port: 54329 }\n"
        "floor: { min_gap_ms: 1500, max_words: 30 }\n",
        encoding="utf-8",
    )
    return d


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_shipped_defaults_load_and_match_model_defaults() -> None:
    loaded = load_config(app_config_dir=REPO_CONFIG, user_config=False)
    assert loaded == TitanConfig()
    assert loaded.api.port == 8765
    assert loaded.postgres.port == 54329
    assert loaded.redis.url == "redis://127.0.0.1:63790/0"
    assert loaded.features.actions is False


def test_layer_precedence(app_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user = write(
        tmp_path / "user.yaml", "api: { port: 9001 }\nfloor: { max_words: 25 }\nchroma: { port: 9100 }\n"
    )
    db = {"api": {"port": 9002}, "floor": {"min_gap_ms": 2000}}
    monkeypatch.setenv("TITAN__API__PORT", "9003")
    monkeypatch.setenv("TITAN__LOGGING__LEVEL", "DEBUG")

    without_cli = load_config(app_config_dir=app_dir, user_config=user, db_settings=db)
    assert without_cli.api.port == 9003  # env beats settings table and files
    assert without_cli.floor.min_gap_ms == 2000  # settings table beats app yaml
    assert without_cli.floor.max_words == 25  # user yaml beats app yaml
    assert without_cli.chroma.port == 9100  # user yaml only
    assert without_cli.logging.level == "DEBUG"
    assert without_cli.api.host == "127.0.0.1"  # deep merge keeps sibling keys

    with_cli = load_config(
        app_config_dir=app_dir, user_config=user, db_settings=db, cli_overrides={"api": {"port": 9004}}
    )
    assert with_cli.api.port == 9004  # CLI beats everything


def test_unknown_keys_fail(app_dir: Path, tmp_path: Path) -> None:
    user = write(tmp_path / "user.yaml", "api: { prot: 1 }\n")
    with pytest.raises(ValidationError):
        load_config(app_config_dir=app_dir, user_config=user)
    bad_section = write(tmp_path / "user2.yaml", "telemetri: {}\n")
    with pytest.raises(ValidationError):
        load_config(app_config_dir=app_dir, user_config=bad_section)


def test_invalid_values_fail(app_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN__AGENTS__TICK_INTERVAL_MS", "500")
    with pytest.raises(ValidationError):
        load_config(app_config_dir=app_dir, user_config=False)


def test_non_mapping_yaml_fails(app_dir: Path, tmp_path: Path) -> None:
    user = write(tmp_path / "user.yaml", "- a\n- b\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(app_config_dir=app_dir, user_config=user)


def test_missing_and_empty_user_files_are_ignored(app_dir: Path, tmp_path: Path) -> None:
    assert load_config(app_config_dir=app_dir, user_config=tmp_path / "nope.yaml").api.port == 8765
    empty = write(tmp_path / "empty.yaml", "")
    assert load_config(app_config_dir=app_dir, user_config=empty).api.port == 8765


def test_default_user_file_location(app_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    write(tmp_path / "roaming" / "Titan" / "config" / "titan.yaml", "api: { port: 9200 }\n")
    assert cfg_mod.user_config_file() == tmp_path / "roaming" / "Titan" / "config" / "titan.yaml"
    assert load_config(app_config_dir=app_dir).api.port == 9200


def test_postgres_password_from_env_is_secret(app_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN__POSTGRES__PASSWORD", "p@ss/word")
    loaded = load_config(app_config_dir=app_dir, user_config=False)
    assert loaded.postgres.password is not None
    assert "p@ss" not in repr(loaded.postgres)
    assert (
        loaded.postgres.sqlalchemy_url() == "postgresql+asyncpg://titan:p%40ss%2Fword@127.0.0.1:54329/titan"
    )
    no_password = cfg_mod.PostgresConfig()
    assert no_password.sqlalchemy_url("psycopg") == "postgresql+psycopg://titan@127.0.0.1:54329/titan"


def test_find_app_config_dir(app_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = app_dir.parent / "a" / "b"
    nested.mkdir(parents=True)
    assert find_app_config_dir(nested) == app_dir
    monkeypatch.setenv(cfg_mod.CONFIG_DIR_ENV, str(tmp_path / "elsewhere"))
    assert find_app_config_dir(nested) == tmp_path / "elsewhere"
    monkeypatch.delenv(cfg_mod.CONFIG_DIR_ENV)
    with pytest.raises(FileNotFoundError):
        find_app_config_dir(Path(tmp_path.anchor))


def test_find_app_config_dir_defaults_to_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_CONFIG.parent)
    assert find_app_config_dir() == REPO_CONFIG


def test_expand_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert expand_path("%LOCALAPPDATA%/Titan/data/pg") == tmp_path / "local" / "Titan" / "data" / "pg"
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert expand_path("%USERPROFILE%/Videos") == Path.home() / "Videos"
    monkeypatch.delenv("TITAN_SURELY_UNSET", raising=False)
    with pytest.raises(KeyError):
        expand_path("%TITAN_SURELY_UNSET%/x")


def test_deep_merge() -> None:
    assert deep_merge({"a": {"b": 1, "c": 2}, "d": 1}, {"a": {"b": 3}, "e": 4}) == {
        "a": {"b": 3, "c": 2},
        "d": 1,
        "e": 4,
    }
