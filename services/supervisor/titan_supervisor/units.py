"""Supervised units: managed child processes, one-shot jobs and externally run services."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import psutil

from titan_core.health import Check
from titan_core.logging import get_logger
from titan_core.protocol.system import DependencyState, ProcessKind
from titan_supervisor import procutil

log = get_logger(__name__)

OutputSink = Callable[[str, str], None]
"""`(unit name, line)` for each line a child writes to stdout or stderr."""

OUTPUT_TAIL = 50


def print_output(name: str, line: str) -> None:
    print(f"[{name}] {line}", file=sys.stderr, flush=True)


class UnitError(RuntimeError):
    """A unit cannot start; the message is shown to the user as the service's detail."""


class Unit(ABC):
    kind: ProcessKind = "managed"

    def __init__(self, name: str, *, requires: Sequence[str] = ()) -> None:
        self.name = name
        self.requires = tuple(requires)

    @property
    @abstractmethod
    def pid(self) -> int | None: ...

    @abstractmethod
    async def start(self) -> None:
        """Launch the process. Raises `UnitError` (or OSError) when it cannot be launched."""

    @abstractmethod
    async def wait(self) -> int | None:
        """Return when the process has exited, with its exit code when known."""

    @abstractmethod
    async def check(self) -> DependencyState: ...

    @abstractmethod
    async def stop(self, timeout_s: float) -> None: ...


class ChildUnit(Unit):
    """A child process the supervisor starts, health-checks and restarts."""

    def __init__(
        self,
        name: str,
        argv: Sequence[str] | Callable[[], Sequence[str]],
        *,
        health: Check | None = None,
        env: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
        cwd: Path | None = None,
        requires: Sequence[str] = (),
        output: OutputSink = print_output,
    ) -> None:
        super().__init__(name, requires=requires)
        self._argv = argv
        self._health = health
        self._env = env
        self._cwd = cwd
        self._output = output
        self._proc: asyncio.subprocess.Process | None = None
        self._pump: asyncio.Task[None] | None = None
        self._tree: dict[int, psutil.Process] = {}
        self.tail: deque[str] = deque(maxlen=OUTPUT_TAIL)

    @property
    def pid(self) -> int | None:
        if self._proc is None or self._proc.returncode is not None:
            return None
        return self._proc.pid

    def argv(self) -> list[str]:
        return list(self._argv() if callable(self._argv) else self._argv)

    async def start(self) -> None:
        argv = self.argv()
        env = self._env() if callable(self._env) else self._env
        self._proc = await procutil.spawn(argv, env=env, cwd=self._cwd)
        self._tree = {}
        log.info("child_spawned", unit=self.name, pid=self._proc.pid, argv=argv[:4])
        self._pump = asyncio.create_task(self._forward(self._proc), name=f"{self.name}-output")

    async def _forward(self, proc: asyncio.subprocess.Process) -> None:
        if proc.stdout is None:
            return
        while line := await proc.stdout.readline():
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self.tail.append(text)
                self._output(self.name, text)

    def _track_tree(self) -> None:
        """Remember the process tree, so grandchildren can be killed if the child dies first."""
        if self._proc is not None and self._proc.returncode is None:
            for process in procutil.descendants(self._proc.pid):
                self._tree.setdefault(process.pid, process)

    def _kill_leftovers(self) -> None:
        alive = [p for p in self._tree.values() if p.is_running()]
        if alive:
            log.warning("child_leftovers_killed", unit=self.name, pids=[p.pid for p in alive])
            procutil.kill_all(alive)
        self._tree = {}

    async def wait(self) -> int | None:
        proc = self._proc
        if proc is None:
            return None
        while not await procutil.wait_exit(proc, 0.5):
            self._track_tree()
        self._kill_leftovers()
        if self._pump is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(self._pump), 1.0)
        return proc.returncode

    async def check(self) -> DependencyState:
        if self._proc is None or self._proc.returncode is not None:
            return DependencyState(state="down", detail="not running")
        if self._health is None:
            return DependencyState(state="up")
        return await self._health()

    async def stop(self, timeout_s: float) -> None:
        if self._proc is not None:
            self._track_tree()
            await procutil.terminate_tree(self._proc, timeout_s)
            self._kill_leftovers()
        if self._pump is not None:
            self._pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump
            self._pump = None


class OneShotUnit(ChildUnit):
    """Runs to completion once per supervisor start (exit code 0), retried with backoff on failure."""

    kind: ProcessKind = "oneshot"


class ExternalUnit(Unit):
    """A service someone else runs (Memurai as a Windows service, or a dev container): health only."""

    kind: ProcessKind = "external"

    def __init__(self, name: str, health: Check, *, requires: Sequence[str] = ()) -> None:
        super().__init__(name, requires=requires)
        self._health = health
        self._stopped = asyncio.Event()

    @property
    def pid(self) -> int | None:
        return None

    async def start(self) -> None:
        self._stopped.clear()

    async def wait(self) -> int | None:
        await self._stopped.wait()
        return None

    async def check(self) -> DependencyState:
        return await self._health()

    async def stop(self, timeout_s: float) -> None:
        self._stopped.set()
