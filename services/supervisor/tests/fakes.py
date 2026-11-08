"""Scriptable fake units for supervisor tests."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Sequence

from titan_core.protocol.system import DependencyState
from titan_supervisor.backoff import RestartPolicy
from titan_supervisor.core import Timing
from titan_supervisor.units import ExternalUnit, OneShotUnit, Unit, UnitError

FAST = Timing(
    start_timeout_s=1.0,
    poll_s=0.01,
    health_interval_s=0.02,
    check_timeout_s=0.2,
    unhealthy_after=3,
    restart_unhealthy_after=5,
    stop_timeout_s=0.5,
)
_pids = itertools.count(1000)


def fast_policy() -> RestartPolicy:
    """The real 1 s / 2 s / 4 s ladder scaled down 100x: same failure counts and circuit window."""
    return RestartPolicy(initial_s=0.01, max_s=0.3)


class FakeProcess(Unit):
    def __init__(
        self,
        name: str,
        *,
        requires: Sequence[str] = (),
        fail_starts: int = 0,
        healthy_after: int = 0,
        log: list[str] | None = None,
    ) -> None:
        super().__init__(name, requires=requires)
        self.fail_starts = fail_starts
        self.healthy_after = healthy_after
        self.healthy = True
        self.starts = 0
        self.stops = 0
        self.log = log if log is not None else []
        self._pid: int | None = None
        self._exited = asyncio.Event()
        self._checks = 0

    @property
    def pid(self) -> int | None:
        return self._pid

    async def start(self) -> None:
        self.starts += 1
        self.log.append(f"start {self.name}")
        if self.fail_starts > 0:
            self.fail_starts -= 1
            raise UnitError(f"{self.name} failed to start")
        self._exited = asyncio.Event()
        self._pid = next(_pids)
        self._checks = 0

    def crash(self) -> None:
        self._pid = None
        self._exited.set()

    async def wait(self) -> int | None:
        await self._exited.wait()
        return 1

    async def check(self) -> DependencyState:
        self._checks += 1
        if self._pid is None:
            return DependencyState(state="down", detail="not running")
        if self._checks <= self.healthy_after or not self.healthy:
            return DependencyState(state="down", detail="not answering")
        return DependencyState(state="up", version="1.0")

    async def stop(self, timeout_s: float) -> None:
        self.stops += 1
        self.log.append(f"stop {self.name}")
        self.crash()


class FakeOneShot(OneShotUnit):
    def __init__(self, name: str, *, exit_codes: Sequence[int] = (0,), requires: Sequence[str] = ()) -> None:
        super().__init__(name, ["unused"], requires=requires)
        self.exit_codes = list(exit_codes)
        self.runs = 0

    @property
    def pid(self) -> int | None:
        return None

    async def start(self) -> None:
        self.runs += 1

    async def wait(self) -> int | None:
        await asyncio.sleep(0.01)
        return self.exit_codes.pop(0) if self.exit_codes else 0

    async def stop(self, timeout_s: float) -> None:
        return None


class FakeExternal(ExternalUnit):
    def __init__(self, name: str) -> None:
        self.up = True
        super().__init__(name, self._health)

    async def _health(self) -> DependencyState:
        return DependencyState(state="up", version="7.0") if self.up else DependencyState(state="down")
