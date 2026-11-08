"""ChildUnit and procutil against real child processes (portable: Linux and Windows CI)."""

from __future__ import annotations

import asyncio
import sys
import textwrap
import time
from pathlib import Path

import psutil
import pytest

from titan_core.protocol.system import DependencyState
from titan_supervisor import procutil
from titan_supervisor.units import ChildUnit, OneShotUnit

PY = sys.executable


def script(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "child.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return [PY, str(path)]


async def wait_for(predicate, timeout_s: float = 10.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout_s
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.05)


async def test_child_output_is_forwarded_and_kept(tmp_path: Path) -> None:
    lines: list[tuple[str, str]] = []
    unit = ChildUnit(
        "echo",
        script(tmp_path, "print('hello', flush=True)\nimport sys; sys.exit(3)"),
        output=lambda name, line: lines.append((name, line)),
    )
    await unit.start()
    assert await asyncio.wait_for(unit.wait(), 10) == 3
    assert lines == [("echo", "hello")]
    assert list(unit.tail) == ["hello"]
    assert unit.pid is None
    assert (await unit.check()).state == "down"


async def test_env_and_health_callables(tmp_path: Path) -> None:
    seen: list[str] = []

    async def health() -> DependencyState:
        return DependencyState(state="up", version="9")

    unit = ChildUnit(
        "envy",
        script(tmp_path, "import os, time; print(os.environ['TITAN_X'], flush=True); time.sleep(30)"),
        env=lambda: {**__import__("os").environ, "TITAN_X": "from-env"},
        health=health,
        output=lambda _name, line: seen.append(line),
    )
    await unit.start()
    try:
        await wait_for(lambda: seen == ["from-env"])
        assert (await unit.check()).version == "9"
        assert unit.pid is not None
    finally:
        await unit.stop(5)
    assert unit.pid is None


async def test_stop_kills_the_whole_tree(tmp_path: Path) -> None:
    argv = script(
        tmp_path,
        f"""
        import subprocess, sys, time
        child = subprocess.Popen([{PY!r}, "-c", "import time; time.sleep(60)"])
        print(child.pid, flush=True)
        time.sleep(60)
        """,
    )
    pids: list[int] = []
    unit = ChildUnit("tree", argv, output=lambda _n, line: pids.append(int(line)))
    await unit.start()
    await wait_for(lambda: bool(pids))
    grandchild = psutil.Process(pids[0])
    await unit.stop(5)
    await wait_for(lambda: not procutil.pid_alive(grandchild.pid))


async def test_grandchild_left_behind_by_a_crash_is_killed(tmp_path: Path) -> None:
    """Like `uvx chroma`: the direct child dies, the real server would otherwise live on."""
    argv = script(
        tmp_path,
        f"""
        import subprocess, sys, time
        child = subprocess.Popen([{PY!r}, "-c", "import time; time.sleep(60)"])
        print(child.pid, flush=True)
        time.sleep(60)
        """,
    )
    pids: list[int] = []
    unit = ChildUnit("wrapper", argv, output=lambda _n, line: pids.append(int(line)))
    await unit.start()
    await wait_for(lambda: bool(pids))
    waiter = asyncio.create_task(unit.wait())
    await asyncio.sleep(0.7)
    assert unit.pid is not None
    psutil.Process(unit.pid).kill()
    await asyncio.wait_for(waiter, 10)
    await wait_for(lambda: not procutil.pid_alive(pids[0]))


async def test_oneshot_kind() -> None:
    unit = OneShotUnit("migrate", [PY, "-c", "pass"])
    assert unit.kind == "oneshot"
    await unit.start()
    assert await asyncio.wait_for(unit.wait(), 10) == 0


async def test_wait_exit_times_out_for_a_running_process() -> None:
    proc = await procutil.spawn([PY, "-c", "import time; time.sleep(30)"])
    try:
        assert not await procutil.wait_exit(proc, 0.3)
    finally:
        await procutil.terminate_tree(proc, 5)
    assert proc.returncode is not None


def test_pid_alive() -> None:
    assert procutil.pid_alive(psutil.Process().pid)
    assert not procutil.pid_alive(None)
    assert not procutil.pid_alive(2**22 + 12345)


def test_spawn_flags_per_platform() -> None:
    windows = procutil.spawn_kwargs("win32")
    assert windows["creationflags"] & procutil.BELOW_NORMAL_PRIORITY_CLASS
    assert windows["creationflags"] & procutil.CREATE_NO_WINDOW
    assert "preexec_fn" in procutil.spawn_kwargs("linux")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is Linux-only")
async def test_linux_children_die_with_the_supervisor(tmp_path: Path) -> None:
    """A stand-in supervisor spawns a child through procutil and is then SIGKILLed."""
    pidfile = tmp_path / "child.pid"
    fake_supervisor = textwrap.dedent(
        f"""
        import asyncio, pathlib
        from titan_supervisor import procutil

        async def main():
            proc = await procutil.spawn([{PY!r}, "-c", "import time; time.sleep(60)"])
            pathlib.Path({str(pidfile)!r}).write_text(str(proc.pid))
            await asyncio.sleep(60)

        asyncio.run(main())
        """
    )
    parent = psutil.Popen([PY, "-c", fake_supervisor])
    await wait_for(lambda: pidfile.exists() and pidfile.read_text() != "")
    child = int(pidfile.read_text())
    assert procutil.pid_alive(child)
    parent.kill()
    parent.wait(10)
    await wait_for(lambda: not procutil.pid_alive(child), timeout_s=5)


@pytest.mark.skipif(sys.platform != "win32", reason="job objects are Windows-only")
async def test_windows_job_kills_children_when_closed(tmp_path: Path) -> None:
    """The supervisor's job object (KILL_ON_JOB_CLOSE): closing the last handle kills members."""
    pidfile = tmp_path / "child.pid"
    fake_supervisor = textwrap.dedent(
        f"""
        import asyncio, pathlib
        from titan_supervisor import procutil
        from titan_supervisor.winjob import create_job

        async def main():
            job = create_job()
            job.assign_current_process()
            proc = await procutil.spawn([{PY!r}, "-c", "import time; time.sleep(60)"])
            pathlib.Path({str(pidfile)!r}).write_text(str(proc.pid))
            await asyncio.sleep(60)

        asyncio.run(main())
        """
    )
    parent = psutil.Popen([PY, "-c", fake_supervisor])
    await wait_for(lambda: pidfile.exists() and pidfile.read_text() != "")
    child = int(pidfile.read_text())
    assert procutil.pid_alive(child)
    parent.kill()  # TerminateProcess: no cleanup code runs; only the job object can help
    parent.wait(10)
    await wait_for(lambda: not procutil.pid_alive(child), timeout_s=5)


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows fallback")
def test_no_job_object_off_windows() -> None:
    from titan_supervisor.winjob import create_job

    assert create_job() is None
