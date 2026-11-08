from __future__ import annotations

import asyncio
import os
import shutil
import socket
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import keyring
import keyring.backend
import keyring.errors
import pytest

from titan_core.config import PostgresConfig
from titan_core.secrets import get_secret
from titan_supervisor import procutil
from titan_supervisor.postgres import (
    CONF_MARKER,
    PostgresUnit,
    UnitError,
    find_bin_dir,
    last_fatal,
    parse_major,
    read_postmaster_pid,
    titan_conf,
)

BIN_DIR = find_bin_dir(os.environ.get("TITAN__POSTGRES__BIN_DIR"), Path.cwd())
needs_binaries = pytest.mark.skipif(BIN_DIR is None, reason="PostgreSQL 16 binaries not found")


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.store.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError(username)


def leftover_pwfiles(root: Path) -> list[Path]:
    return list(root.glob(".initdb-pw-*"))


@pytest.fixture
def pg_root(tmp_path: Path) -> Iterator[Path]:
    """pytest's tmp dirs are owner-only on Windows (Python 3.12 `mkdir(mode=0o700)`), and initdb and
    postgres run with a restricted token that cannot open them; use a folder that inherits the
    user's temp-folder ACL instead."""
    if sys.platform != "win32":
        yield tmp_path
        return
    root = Path(tempfile.gettempdir()) / f"titan-pgtest-{uuid.uuid4().hex[:8]}"
    root.mkdir()
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def memory_keyring() -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_parse_major() -> None:
    assert parse_major("pg_ctl (PostgreSQL) 16.15") == 16
    assert parse_major("pg_ctl (PostgreSQL) 17.2 (Ubuntu 17.2-1)") == 17
    assert parse_major("nonsense") is None


def test_titan_conf_is_loopback_tcp_only() -> None:
    conf = titan_conf(54329)
    assert CONF_MARKER in conf
    assert "listen_addresses = '127.0.0.1'" in conf
    assert "port = 54329" in conf
    assert "unix_socket_directories = ''" in conf


def test_postmaster_pid_and_fatal_line(tmp_path: Path) -> None:
    assert read_postmaster_pid(tmp_path) is None
    (tmp_path / "postmaster.pid").write_text("4321\n/data\n", encoding="utf-8")
    assert read_postmaster_pid(tmp_path) == 4321
    log = tmp_path / "pg.log"
    assert last_fatal(log) is None
    log.write_text('LOG:  starting\nFATAL:  could not bind IPv4 address "127.0.0.1"\n', encoding="utf-8")
    assert last_fatal(log) == 'could not bind IPv4 address "127.0.0.1"'


def test_find_bin_dir_prefers_config(tmp_path: Path) -> None:
    exe = ".exe" if os.name == "nt" else ""
    (tmp_path / f"pg_ctl{exe}").write_bytes(b"")
    assert find_bin_dir(str(tmp_path), None) == tmp_path


async def test_missing_binaries_is_a_clear_error(tmp_path: Path) -> None:
    unit = PostgresUnit(PostgresConfig(password="x"), None, data_dir=tmp_path / "pg")
    with pytest.raises(UnitError, match="fetch-third-party"):
        await unit.start()


async def test_non_cluster_data_dir_is_refused(tmp_path: Path) -> None:
    if BIN_DIR is None:
        pytest.skip("PostgreSQL 16 binaries not found")
    data = tmp_path / "pg"
    data.mkdir()
    (data / "stray.txt").write_text("not a cluster", encoding="utf-8")
    unit = PostgresUnit(PostgresConfig(password="x", port=free_port()), BIN_DIR, data_dir=data)
    with pytest.raises(UnitError, match="not empty"):
        await unit.start()


@needs_binaries
async def test_first_run_initdb_keyring_password_and_restart(
    pg_root: Path, memory_keyring: MemoryKeyring
) -> None:
    """M1.T1: initdb on first run with a random password kept in the keyring, loopback only."""
    cfg = PostgresConfig(port=free_port(), password=None, database="titan")
    data = pg_root / "pg"
    passwords: list[str] = []
    unit = PostgresUnit(
        cfg, BIN_DIR, data_dir=data, log_file=pg_root / "pg.log", on_password=passwords.append
    )
    await unit.start()
    try:
        stored = get_secret("postgres")
        assert stored is not None
        assert len(stored) >= 40
        assert passwords == [stored]
        assert leftover_pwfiles(pg_root) == []
        assert (await unit.check()).state == "up"
        assert unit.pid is not None
        conf = (data / "postgresql.conf").read_text(encoding="utf-8")
        assert conf.count(CONF_MARKER) == 1
        hba = (data / "pg_hba.conf").read_text(encoding="utf-8").splitlines()
        assert [line for line in hba if not line.startswith("#")] == [
            "host all all 127.0.0.1/32 scram-sha-256"
        ]
        conn = await asyncpg.connect(
            host="127.0.0.1", port=cfg.port, user="titan", password=stored, database="titan"
        )
        try:
            assert await conn.fetchval("SHOW listen_addresses") == "127.0.0.1"
            assert await conn.fetchval("SHOW unix_socket_directories") == ""
            assert await conn.fetchval("SHOW password_encryption") == "scram-sha-256"
        finally:
            await conn.close()
        with pytest.raises(asyncpg.InvalidPasswordError):
            await asyncpg.connect(host="127.0.0.1", port=cfg.port, user="titan", password="wrong")

        # Killing the postmaster is noticed by wait(); a fresh start reuses the cluster.
        waiter = asyncio.create_task(unit.wait())
        procutil.kill_tree_by_pid(unit.pid)
        await asyncio.wait_for(waiter, 10)
        assert (await unit.check()).state == "down"
        await unit.start()
        assert get_secret("postgres") == stored
        assert (await unit.check()).state == "up"
    finally:
        await unit.stop(10)
    assert unit.pid is None
    assert read_postmaster_pid(data) is None


@needs_binaries
async def test_start_adopts_a_running_server(pg_root: Path) -> None:
    cfg = PostgresConfig(port=free_port(), password="adopt-me")
    first = PostgresUnit(cfg, BIN_DIR, data_dir=pg_root / "pg", log_file=pg_root / "pg.log")
    await first.start()
    try:
        pid = first.pid
        second = PostgresUnit(cfg, BIN_DIR, data_dir=pg_root / "pg", log_file=pg_root / "pg.log")
        await second.start()
        assert second.pid == pid
    finally:
        await first.stop(10)


@needs_binaries
async def test_existing_cluster_without_a_keyring_password_is_an_error(
    pg_root: Path, memory_keyring: MemoryKeyring
) -> None:
    (pg_root / "pg").mkdir()
    (pg_root / "pg" / "PG_VERSION").write_text("16\n", encoding="utf-8")
    unit = PostgresUnit(PostgresConfig(password=None, port=free_port()), BIN_DIR, data_dir=pg_root / "pg")
    with pytest.raises(UnitError, match="keyring has no titan/postgres"):
        await unit.start()


@needs_binaries
async def test_port_in_use_reports_the_postgres_fatal_line(pg_root: Path) -> None:
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        unit = PostgresUnit(
            PostgresConfig(password="x", port=port),
            BIN_DIR,
            data_dir=pg_root / "pg",
            log_file=pg_root / "pg.log",
        )
        with pytest.raises(UnitError, match="could not"):
            await unit.start()
