"""Portable PostgreSQL 16 management (M1.T1, decision D1).

First run: `initdb` with a random superuser password stored in the OS keyring as `titan/postgres`
(Windows Credential Manager), TCP on 127.0.0.1 only, no Unix sockets. Every start: `pg_ctl start`,
then create the `titan` database if it is missing. Stop: `pg_ctl stop -m fast`.

`pg_ctl` (rather than running `postgres` directly) is required on Windows: it drops administrator
rights with a restricted token, and postgres refuses to run elevated. The postmaster it starts
joins the supervisor's job object, so it still dies with the supervisor.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import secrets as _random
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import asyncpg
from pydantic import SecretStr

from titan_core.config import PostgresConfig, expand_path
from titan_core.health import check_postgres
from titan_core.logging import get_logger
from titan_core.protocol.system import DependencyState
from titan_core.secrets import SecretStoreUnavailable, generate_password, get_secret, set_secret
from titan_supervisor import procutil
from titan_supervisor.units import Unit, UnitError

log = get_logger(__name__)

REQUIRED_MAJOR = 16
SECRET_NAME = "postgres"  # noqa: S105 (keyring entry name)
CONF_MARKER = "# --- Titan (M1.T1) ---"
PG_HBA = (
    "# Titan (Section 9.6): TCP from loopback only, SCRAM passwords.\n"
    "host all all 127.0.0.1/32 scram-sha-256\n"
)
EXE = ".exe" if sys.platform == "win32" else ""
_VERSION = re.compile(r"\(PostgreSQL\)\s+(\d+)(?:\.(\d+))?")


def _has_pg_ctl(path: Path) -> bool:
    return (path / f"pg_ctl{EXE}").is_file()


def find_bin_dir(configured: str | None, app_dir: Path | None) -> Path | None:
    """Locate PostgreSQL binaries: config, then the bundled copy (`<app>/pgsql/bin`), then the
    developer copy from `tools/fetch-third-party.py`, then `pg_config --bindir`."""
    candidates: list[Path] = []
    if configured:
        candidates.append(expand_path(configured))
    if app_dir is not None:
        candidates += [
            app_dir / "pgsql" / "bin",
            app_dir / "third_party" / "cache" / "postgresql" / "pgsql" / "bin",
        ]
    pg_config = shutil.which("pg_config")
    if pg_config:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            out = subprocess.run(  # noqa: S603 (pg_config found on PATH)
                [pg_config, "--bindir"], capture_output=True, text=True, timeout=5, check=True
            )
            candidates.append(Path(out.stdout.strip()))
    candidates.append(Path(f"/usr/lib/postgresql/{REQUIRED_MAJOR}/bin"))
    return next((c for c in candidates if _has_pg_ctl(c)), None)


def parse_major(version_output: str) -> int | None:
    match = _VERSION.search(version_output)
    return int(match.group(1)) if match else None


def read_postmaster_pid(data_dir: Path) -> int | None:
    try:
        first = (data_dir / "postmaster.pid").read_text(encoding="utf-8").splitlines()[0]
        return int(first.strip())
    except (OSError, IndexError, ValueError):
        return None


def last_fatal(log_file: Path) -> str | None:
    """The last FATAL line of the server log, which says why a start failed."""
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
    except OSError:
        return None
    fatal = [line.split("FATAL:", 1)[1].strip() for line in lines if "FATAL:" in line]
    return fatal[-1] if fatal else None


def titan_conf(port: int) -> str:
    return (
        f"\n{CONF_MARKER}\n"
        "listen_addresses = '127.0.0.1'\n"
        f"port = {port}\n"
        "unix_socket_directories = ''\n"
        "password_encryption = 'scram-sha-256'\n"
    )


class PostgresUnit(Unit):
    def __init__(
        self,
        cfg: PostgresConfig,
        bin_dir: Path | None,
        *,
        data_dir: Path | None = None,
        log_file: Path | None = None,
        poll_s: float = 0.5,
        on_password: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__("postgres")
        self.cfg = cfg
        self.bin_dir = bin_dir
        self.data_dir = data_dir or expand_path(cfg.data_dir)
        self.log_file = log_file or self.data_dir.parent / "postgres.log"
        self._poll_s = poll_s
        self._on_password = on_password
        self._pid: int | None = None
        self.password: str | None = None

    @property
    def pid(self) -> int | None:
        return self._pid if procutil.pid_alive(self._pid) else None

    def _tool(self, name: str) -> str:
        if self.bin_dir is None:
            raise UnitError(
                "PostgreSQL 16 binaries not found: run `uv run python tools/fetch-third-party.py "
                "postgresql --extract` or set postgres.bin_dir"
            )
        return str(self.bin_dir / f"{name}{EXE}")

    async def _run(self, *args: str, timeout_s: float = 60) -> tuple[int, str]:
        # Output goes to a file, not a pipe: on Windows the postmaster that `pg_ctl start` launches
        # inherits pg_ctl's handles, and would hold a pipe open for as long as it runs.
        with tempfile.TemporaryFile() as output:
            proc = await procutil.spawn(list(args), stdout=output)
            if not await procutil.wait_exit(proc, timeout_s):
                await procutil.terminate_tree(proc, 2)
                raise UnitError(f"{Path(args[0]).name} timed out after {timeout_s:g}s")
            output.seek(0)
            out = output.read()
        return proc.returncode or 0, out.decode("utf-8", errors="replace").strip()

    async def _check_version(self) -> None:
        code, out = await self._run(self._tool("pg_ctl"), "--version", timeout_s=10)
        major = parse_major(out)
        if code != 0 or major != REQUIRED_MAJOR:
            raise UnitError(
                f"PostgreSQL {REQUIRED_MAJOR} required (D1), found {out or 'nothing'} in {self.bin_dir}"
            )

    def _resolve_password(self, *, creating: bool) -> str:
        if self.cfg.password is not None:
            return self.cfg.password.get_secret_value()
        try:
            stored = get_secret(SECRET_NAME)
        except SecretStoreUnavailable as exc:
            raise UnitError(f"no OS keyring available ({exc}); set TITAN__POSTGRES__PASSWORD") from exc
        if stored:
            return stored
        if not creating:
            raise UnitError("the cluster exists but the keyring has no titan/postgres password")
        password = generate_password()
        set_secret(SECRET_NAME, password)
        log.info("postgres_password_stored", keyring_entry=SECRET_NAME)
        return password

    def initialized(self) -> bool:
        return (self.data_dir / "PG_VERSION").is_file()

    async def _initdb(self, password: str) -> None:
        if self.data_dir.exists() and any(self.data_dir.iterdir()):
            raise UnitError(f"{self.data_dir} is not empty and is not a PostgreSQL cluster")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Not in tempfile.mkdtemp(): on Windows that folder is owner-only, and initdb drops
        # administrator rights with a restricted token that can no longer open it.
        pwfile = self.data_dir.parent / f".initdb-pw-{_random.token_hex(8)}"
        fd = os.open(pwfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(password)
            code, out = await self._run(
                self._tool("initdb"),
                "-D", str(self.data_dir),
                "-U", self.cfg.user,
                f"--pwfile={pwfile}",
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
                "--no-instructions",
                timeout_s=180,
            )  # fmt: skip
        finally:
            pwfile.unlink(missing_ok=True)
        if code != 0:
            raise UnitError(f"initdb failed: {out[-400:]}")
        with (self.data_dir / "postgresql.conf").open("a", encoding="utf-8") as conf:
            conf.write(titan_conf(self.cfg.port))
        (self.data_dir / "pg_hba.conf").write_text(PG_HBA, encoding="utf-8")
        log.info("postgres_initialized", data_dir=str(self.data_dir))

    async def start(self) -> None:
        await self._check_version()
        creating = not self.initialized()
        password = self._resolve_password(creating=creating)
        if creating:
            await self._initdb(password)
        self.password = password
        if self._on_password is not None:
            self._on_password(password)
        code, _ = await self._run(self._tool("pg_ctl"), "status", "-D", str(self.data_dir), timeout_s=10)
        if code == 0:
            log.warning("postgres_adopted", pid=read_postmaster_pid(self.data_dir))
        else:
            # A hard-killed postmaster leaves a lock file that still says "ready". On Windows
            # `pg_ctl -w` cannot match PIDs and accepts any lock file started within 2 s of
            # itself, so a quick restart would return before the new server is up.
            (self.data_dir / "postmaster.pid").unlink(missing_ok=True)
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            code, out = await self._run(
                self._tool("pg_ctl"), "start",
                "-D", str(self.data_dir),
                "-l", str(self.log_file),
                "-w", "-t", "30", "-s",
                "-o", f"-p {self.cfg.port} -c listen_addresses=127.0.0.1",
                timeout_s=45,
            )  # fmt: skip
            if code != 0:
                raise UnitError(f"pg_ctl start failed: {last_fatal(self.log_file) or out[-300:]}")
        self._pid = read_postmaster_pid(self.data_dir)
        await self._ensure_database(password)
        self._pid = read_postmaster_pid(self.data_dir)

    async def _connect_admin(self, password: str, *, ready_timeout_s: float = 30) -> asyncpg.Connection:
        """Connect to the `postgres` database, waiting out crash recovery after an unclean stop
        (`pg_ctl -w` can return while the server still answers "not yet accepting connections")."""
        deadline = asyncio.get_running_loop().time() + ready_timeout_s
        while True:
            try:
                return await asyncpg.connect(
                    host=self.cfg.host, port=self.cfg.port, user=self.cfg.user, password=password,
                    database="postgres", timeout=10,
                )  # fmt: skip
            except asyncpg.CannotConnectNowError:
                if asyncio.get_running_loop().time() > deadline:
                    raise
                await asyncio.sleep(0.25)

    async def _ensure_database(self, password: str) -> None:
        conn = await self._connect_admin(password)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", self.cfg.database)
            if not exists:
                name = self.cfg.database.replace('"', '""')
                await conn.execute(f'CREATE DATABASE "{name}"')
                log.info("postgres_database_created", database=self.cfg.database)
        finally:
            await conn.close()

    async def wait(self) -> int | None:
        while procutil.pid_alive(self._pid):  # noqa: ASYNC110 (polling another process)
            await asyncio.sleep(self._poll_s)
        return None

    async def check(self) -> DependencyState:
        if not procutil.pid_alive(self._pid):
            return DependencyState(state="down", detail="postmaster not running")
        cfg = (
            self.cfg
            if self.password is None
            else self.cfg.model_copy(update={"password": SecretStr(self.password)})
        )
        return await check_postgres(cfg, database="postgres")

    async def stop(self, timeout_s: float) -> None:
        if not procutil.pid_alive(self._pid):
            self._pid = None
            return
        code, out = await self._run(
            self._tool("pg_ctl"), "stop", "-D", str(self.data_dir), "-m", "fast", "-w",
            "-t", str(int(timeout_s)), "-s", timeout_s=timeout_s + 5,
        )  # fmt: skip
        if code != 0 and procutil.pid_alive(self._pid):
            log.error("postgres_stop_failed", output=out[-300:])
            procutil.kill_tree_by_pid(self._pid)
        self._pid = None
