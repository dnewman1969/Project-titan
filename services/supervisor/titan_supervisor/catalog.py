"""The process table: `supervisor.processes` in config, in start order (Sections 2.3 and 9.5)."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from titan_core.config import TitanConfig, expand_path
from titan_core.health import check_chroma, check_http, check_postgres, check_redis
from titan_core.secrets import resolve_secret
from titan_supervisor.postgres import PostgresUnit, find_bin_dir
from titan_supervisor.units import (
    ChildUnit,
    ExternalUnit,
    OneShotUnit,
    OutputSink,
    Unit,
    UnitError,
    print_output,
)

CHROMA_VERSION = "1.5.9"
"""Pinned to match docker-compose.yml and CI."""


def chroma_command(configured: list[str] | None) -> list[str]:
    """`chroma` next to this interpreter (the bundled venv), else on PATH, else `uvx` (development)."""
    if configured:
        return list(configured)
    exe = Path(sys.executable).with_name("chroma.exe" if sys.platform == "win32" else "chroma")
    if exe.is_file():
        return [str(exe)]
    found = shutil.which("chroma")
    if found:
        return [found]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", f"chromadb=={CHROMA_VERSION}", "chroma"]
    raise UnitError("chroma not found: install chromadb or uv, or set chroma.command")


class ChildEnv:
    """Environment for Titan's own children: the supervisor's environment plus resolved secrets.

    Secrets reach children only through their environment, never through argv or logs.
    """

    def __init__(self, cfg: TitanConfig, base: Mapping[str, str] | None = None) -> None:
        self.cfg = cfg
        self.base = dict(os.environ if base is None else base)
        self.postgres_password: str | None = None

    def __call__(self) -> dict[str, str]:
        env = {**self.base, "PYTHONUNBUFFERED": "1"}
        pg = self.postgres_password or _secret_value(resolve_secret(self.cfg.postgres.password, "postgres"))
        if pg:
            env["TITAN__POSTGRES__PASSWORD"] = pg
        redis = _secret_value(resolve_secret(self.cfg.redis.password, "redis"))
        if redis:
            env["TITAN__REDIS__PASSWORD"] = redis
        return env


def _secret_value(secret: object) -> str | None:
    getter = getattr(secret, "get_secret_value", None)
    return getter() if callable(getter) else None


def build_units(
    cfg: TitanConfig,
    *,
    app_dir: Path | None,
    env: ChildEnv | None = None,
    output: OutputSink = print_output,
    python: str = sys.executable,
) -> list[Unit]:
    child_env = env or ChildEnv(cfg)
    builders: dict[str, Callable[[], Unit]] = {
        "postgres": lambda: _postgres(cfg, app_dir, child_env),
        "redis": lambda: ExternalUnit("redis", lambda: check_redis(cfg.redis)),
        "chroma": lambda: _chroma(cfg, child_env, output),
        "migrate": lambda: OneShotUnit(
            "migrate",
            [python, "-m", "titan_db.cli", "upgrade"],
            env=child_env,
            requires=["postgres"] if "postgres" in cfg.supervisor.processes else [],
            output=output,
        ),
        "api": lambda: ChildUnit(
            "api",
            [python, "-m", "titan_api"],
            health=lambda: check_http(f"http://{cfg.api.host}:{cfg.api.port}/api/v1/health"),
            env=child_env,
            output=output,
        ),
    }
    return [builders[name]() for name in cfg.supervisor.processes]


def _postgres(cfg: TitanConfig, app_dir: Path | None, env: ChildEnv) -> Unit:
    if cfg.postgres.mode == "external":
        return ExternalUnit("postgres", lambda: check_postgres(cfg.postgres))

    def remember(password: str) -> None:
        env.postgres_password = password

    return PostgresUnit(
        cfg.postgres,
        find_bin_dir(cfg.postgres.bin_dir, app_dir),
        log_file=expand_path("%LOCALAPPDATA%/Titan/logs/postgres/postgres.log"),
        on_password=remember,
    )


def _chroma(cfg: TitanConfig, env: ChildEnv, output: OutputSink) -> Unit:
    chroma = cfg.chroma
    if chroma.mode == "external":
        return ExternalUnit("chroma", lambda: check_chroma(chroma))
    data_dir = expand_path(chroma.data_dir)

    def argv() -> list[str]:
        data_dir.mkdir(parents=True, exist_ok=True)
        return [*chroma_command(chroma.command), "run", "--host", chroma.host, "--port", str(chroma.port),
                "--path", str(data_dir)]  # fmt: skip

    def chroma_env() -> dict[str, str]:
        # Chroma >= 1.0 has no built-in auth (see spec M1.T2); it is reachable on loopback only.
        return {**env(), "ANONYMIZED_TELEMETRY": "False"}

    return ChildUnit("chroma", argv, health=lambda: check_chroma(chroma), env=chroma_env, output=output)
