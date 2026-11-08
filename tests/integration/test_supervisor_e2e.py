"""M1 acceptance (Section 10, M1): the real supervisor brings Postgres, Redis, Chroma, migrations and
the API up, restarts a killed child and leaves no process behind.

Needs PostgreSQL 16 binaries (`TITAN__POSTGRES__BIN_DIR`, the third_party/ copy or `pg_config`),
a Redis with `requirepass` (`TITAN__REDIS__PASSWORD`) and, unless `TITAN_E2E_PROCESSES` drops it,
Chroma through `uvx`. Skips unless `TITAN_REQUIRE_SUPERVISOR_E2E=1`.

On Windows the Postgres password goes through the real Credential Manager under a throwaway keyring
service, and a hard kill of the supervisor must take every child with it (job object).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import psutil
import pytest

REPO = Path(__file__).resolve().parents[2]
ENABLED = os.environ.get("TITAN_REQUIRE_SUPERVISOR_E2E") == "1"
START_BUDGET_S = float(os.environ.get("TITAN_E2E_START_BUDGET_S", "20"))
RESTART_BUDGET_S = 10.0
WINDOWS = sys.platform == "win32"

pytestmark = pytest.mark.skipif(not ENABLED, reason="set TITAN_REQUIRE_SUPERVISOR_E2E=1")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for[T](probe: Callable[[], T | None], timeout_s: float, what: str) -> T:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with contextlib.suppress(httpx.HTTPError):
            value = probe()
            if value is not None:
                return value
        time.sleep(0.2)
    raise AssertionError(f"timed out after {timeout_s:.0f}s waiting for {what}")


@dataclass
class Titan:
    root: Path
    env: dict[str, str]
    token: str
    supervisor_url: str
    api_url: str
    keyring_service: str | None
    proc: subprocess.Popen[bytes] | None = None
    seen: dict[int, psutil.Process] = field(default_factory=dict)

    def start(self) -> None:
        log = (self.root / "supervisor.log").open("ab")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "titan_supervisor"],
            cwd=REPO,
            env=self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        log.close()

    def client(self, base: str) -> httpx.Client:
        return httpx.Client(
            base_url=base, headers={"Authorization": f"Bearer {self.token}"}, timeout=2, trust_env=False
        )

    def status(self) -> dict[str, Any]:
        with self.client(self.supervisor_url) as c:
            response = c.get("/status")
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        self.track()
        return body

    def service(self, body: dict[str, Any], name: str) -> dict[str, Any]:
        return next(s for s in body["services"] if s["name"] == name)

    def track(self) -> None:
        """Remember every descendant ever seen, to check none outlives the supervisor."""
        assert self.proc is not None
        with contextlib.suppress(psutil.Error):
            for child in psutil.Process(self.proc.pid).children(recursive=True):
                self.seen.setdefault(child.pid, child)

    def survivors(self) -> list[str]:
        alive = []
        for pid, proc in self.seen.items():
            with contextlib.suppress(psutil.NoSuchProcess):
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    alive.append(f"{pid} {' '.join(proc.cmdline())[:120]}")
        return alive

    def log_tail(self) -> str:
        path = self.root / "supervisor.log"
        return path.read_text(encoding="utf-8", errors="replace")[-6000:] if path.exists() else ""


@pytest.fixture(scope="module")
def titan() -> Iterator[Titan]:
    # Not pytest's tmp_path: on Windows it is owner-only (mkdir mode 0o700), which the restricted
    # token initdb and postgres run under cannot open. This folder inherits the temp folder's ACL.
    root = Path(tempfile.gettempdir()) / f"titan-e2e-{secrets.token_hex(4)}"
    root.mkdir()
    token = secrets.token_urlsafe(24)
    ports = {name: free_port() for name in ("api", "postgres", "chroma", "supervisor")}
    processes = os.environ.get("TITAN_E2E_PROCESSES", "postgres,redis,chroma,migrate,api").split(",")
    env = {
        **os.environ,
        "LOCALAPPDATA": str(root / "local"),
        "APPDATA": str(root / "roaming"),
        "TITAN_LAUNCH_TOKEN": token,
        "TITAN__API__PORT": str(ports["api"]),
        "TITAN__POSTGRES__PORT": str(ports["postgres"]),
        "TITAN__POSTGRES__MODE": "managed",
        "TITAN__CHROMA__PORT": str(ports["chroma"]),
        "TITAN__CHROMA__MODE": "managed",
        "TITAN__SUPERVISOR__PORT": str(ports["supervisor"]),
        "TITAN__SUPERVISOR__PROCESSES": json.dumps(processes),
        "PYTHONUNBUFFERED": "1",
    }
    env.pop("TITAN_PARENT_PID", None)
    keyring_service = None
    if WINDOWS:
        keyring_service = f"titan-e2e-{secrets.token_hex(4)}"
        env["TITAN_KEYRING_SERVICE"] = keyring_service
        env.pop("TITAN__POSTGRES__PASSWORD", None)
    else:
        env.setdefault("TITAN__POSTGRES__PASSWORD", secrets.token_urlsafe(16))
    t = Titan(
        root=root,
        env=env,
        token=token,
        supervisor_url=f"http://127.0.0.1:{ports['supervisor']}",
        api_url=f"http://127.0.0.1:{ports['api']}/api/v1",
        keyring_service=keyring_service,
    )
    yield t
    if t.proc is not None and t.proc.poll() is None:
        t.proc.kill()
        t.proc.wait(10)
    for proc in t.seen.values():
        with contextlib.suppress(psutil.Error):
            proc.kill()
    if keyring_service is not None:
        import keyring
        import keyring.errors

        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(keyring_service, "postgres")
    shutil.rmtree(root, ignore_errors=True)


def wait_ready(t: Titan, budget_s: float) -> float:
    started = time.monotonic()
    try:
        wait_for(lambda: True if t.status()["ready"] else None, budget_s, "every service healthy")
    except AssertionError:
        pytest.fail(f"not ready within {budget_s:.0f}s\n{t.log_tail()}")
    return time.monotonic() - started


def test_cold_start_is_healthy_within_budget(titan: Titan) -> None:
    titan.start()
    elapsed = wait_ready(titan, START_BUDGET_S)
    body = titan.status()
    assert all(s["state"] == "up" for s in body["services"]), body["services"]
    with titan.client(titan.api_url) as api:
        assert api.get("/health").status_code == 200
        status = api.get("/system/status")
        assert api.get("/system/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert status.status_code == 200, status.text
    payload = status.json()
    names = [s["name"] for s in payload["services"]]
    assert names == json.loads(titan.env["TITAN__SUPERVISOR__PROCESSES"])
    assert payload["dependencies"]["postgres"]["state"] == "up"
    assert payload["dependencies"]["redis"]["state"] == "up"
    print(f"cold start healthy in {elapsed:.1f}s")


def test_metrics_reach_the_api(titan: Titan) -> None:
    with titan.client(titan.api_url) as api:
        sample = wait_for(
            lambda: r.json() if (r := api.get("/system/metrics")).status_code == 200 else None,
            5,
            "a system.metrics sample",
        )
    assert 0 <= sample["cpu_pct"] <= 100
    assert sample["ram_used_mb"] > 0
    assert sample["game_fps"] is None


@pytest.mark.parametrize("name", ["api", "postgres", "chroma"])
def test_killed_child_restarts_within_budget(titan: Titan, name: str) -> None:
    if name not in json.loads(titan.env["TITAN__SUPERVISOR__PROCESSES"]):
        pytest.skip(f"{name} is not supervised in this run")
    before = titan.service(titan.status(), name)
    assert before["pid"], before
    last_seq = max((e["seq"] for e in titan.status()["events"]), default=0)
    psutil.Process(before["pid"]).kill()
    killed_at = time.monotonic()

    def restarted() -> dict[str, Any] | None:
        s = titan.service(titan.status(), name)
        ok = (
            s["state"] == "up"
            and s["pid"] not in (None, before["pid"])
            and s["restarts"] > before["restarts"]
        )
        return s if ok else None

    try:
        wait_for(restarted, RESTART_BUDGET_S, f"{name} to restart")
    except AssertionError:
        pytest.fail(f"{name} not back within {RESTART_BUDGET_S:.0f}s\n{titan.log_tail()}")
    elapsed = time.monotonic() - killed_at
    events = [e for e in titan.status()["events"] if e["seq"] > last_seq and e["process"] == name]
    assert any(e["kind"] == "exited" for e in events), events
    assert any(e["kind"] == "healthy" for e in events), events
    print(f"{name} restarted in {elapsed:.1f}s")


def test_shutdown_leaves_no_processes(titan: Titan) -> None:
    assert titan.proc is not None
    titan.track()
    with titan.client(titan.supervisor_url) as c:
        assert c.post("/shutdown").status_code == 202
    assert titan.proc.wait(30) == 0, titan.log_tail()
    deadline = time.monotonic() + 5
    while titan.survivors() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert titan.survivors() == [], titan.log_tail()


@pytest.mark.skipif(not WINDOWS, reason="job object (KILL_ON_JOB_CLOSE) is Windows-only")
def test_hard_kill_takes_every_child_with_it(titan: Titan) -> None:
    titan.seen.clear()
    titan.start()
    wait_ready(titan, START_BUDGET_S)
    titan.track()
    assert titan.seen, "no children seen"
    assert titan.proc is not None
    titan.proc.kill()
    titan.proc.wait(10)
    deadline = time.monotonic() + 5
    while titan.survivors() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert titan.survivors() == []
