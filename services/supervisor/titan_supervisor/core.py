"""The supervisor loop: start order, health checks, restart backoff, circuit breaker (M1.T3)."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from titan_core.clock import utc_now
from titan_core.health import timed
from titan_core.logging import get_logger
from titan_core.protocol.system import (
    ServiceState,
    ServiceStateName,
    SupervisorEvent,
    SupervisorEventKind,
    SupervisorStatus,
)
from titan_supervisor.backoff import RestartPolicy
from titan_supervisor.units import ExternalUnit, OneShotUnit, Unit, UnitError

log = get_logger(__name__)

MAX_EVENTS = 200
HEALTHY = frozenset({"up", "degraded"})


@dataclass(frozen=True)
class Timing:
    start_timeout_s: float = 20.0
    """Soft wait for each unit to become healthy before the next one in the order starts, and the
    hard limit for a starting process to pass its first health check."""
    poll_s: float = 0.25
    """Health-check interval while a process is starting."""
    health_interval_s: float = 2.0
    check_timeout_s: float = 1.5
    unhealthy_after: int = 3
    """Consecutive failed checks before a running process is reported degraded."""
    restart_unhealthy_after: int = 5
    """Consecutive failed checks before a running process is killed and restarted."""
    stop_timeout_s: float = 10.0


@dataclass
class _Slot:
    unit: Unit
    policy: RestartPolicy
    state: ServiceStateName = "unknown"
    detail: str | None = "waiting to start"
    since: datetime = field(default_factory=utc_now)
    restarts: int = 0
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    settled: asyncio.Event = field(default_factory=asyncio.Event)
    """Healthy once, or given up on (circuit open): the start order moves on either way."""
    manual_restart: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class Supervisor:
    def __init__(
        self,
        units: Sequence[Unit],
        *,
        timing: Timing | None = None,
        policy_factory: Callable[[], RestartPolicy] = RestartPolicy,
    ) -> None:
        names = [u.name for u in units]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate unit names: {names}")
        self.timing = timing or Timing()
        self._slots = {u.name: _Slot(u, policy_factory()) for u in units}
        self._events: deque[SupervisorEvent] = deque(maxlen=MAX_EVENTS)
        self._seq = 0
        self._stopping = asyncio.Event()
        self.started_at = utc_now()

    # ------------------------------------------------------------------ public API
    @property
    def names(self) -> list[str]:
        return list(self._slots)

    def unit(self, name: str) -> Unit:
        return self._slots[name].unit

    @property
    def ready(self) -> bool:
        return all(slot.ready.is_set() for slot in self._slots.values())

    def status(self) -> SupervisorStatus:
        return SupervisorStatus(
            started_at=self.started_at,
            ready=self.ready,
            services=[self._service_state(slot) for slot in self._slots.values()],
            events=list(self._events),
        )

    def events_since(self, seq: int) -> list[SupervisorEvent]:
        return [e for e in self._events if e.seq > seq]

    async def start(self) -> None:
        """Start every unit in order, waiting up to `start_timeout_s` for each to become healthy."""
        for slot in self._slots.values():
            slot.task = asyncio.create_task(self._run(slot), name=f"unit-{slot.unit.name}")
            try:
                await asyncio.wait_for(slot.settled.wait(), self.timing.start_timeout_s)
            except TimeoutError:
                log.warning("start_order_timeout", unit=slot.unit.name, waited_s=self.timing.start_timeout_s)
            if self._stopping.is_set():
                return
        log.info("supervisor_started", ready=self.ready)

    async def restart(self, name: str) -> None:
        """Manual restart: closes the circuit breaker and restarts the process now."""
        slot = self._slots[name]
        slot.policy.reset()
        if slot.state == "failed":
            slot.manual_restart.set()
            return
        if isinstance(slot.unit, ExternalUnit):
            return
        await slot.unit.stop(self.timing.stop_timeout_s)

    async def stop(self) -> None:
        """Stop every unit in reverse start order."""
        self._stopping.set()
        for slot in self._slots.values():
            slot.manual_restart.set()
        tasks = [slot.task for slot in self._slots.values() if slot.task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for slot in reversed(list(self._slots.values())):
            try:
                await slot.unit.stop(self.timing.stop_timeout_s)
            except (OSError, UnitError) as exc:
                log.error("unit_stop_failed", unit=slot.unit.name, error=str(exc))
            self._set(slot, "stopped", None)
            self._emit(slot, "stopped")
        log.info("supervisor_stopped")

    # ------------------------------------------------------------------ internals
    def _service_state(self, slot: _Slot) -> ServiceState:
        return ServiceState(
            name=slot.unit.name,
            state=slot.state,
            pid=slot.unit.pid,
            restarts=slot.restarts,
            since=slot.since,
            detail=slot.detail,
            kind=slot.unit.kind,
        )

    def _set(self, slot: _Slot, state: ServiceStateName, detail: str | None) -> None:
        if slot.state != state:
            slot.since = utc_now()
        slot.state = state
        slot.detail = detail

    def _emit(self, slot: _Slot, kind: SupervisorEventKind, detail: str | None = None) -> None:
        self._seq += 1
        event = SupervisorEvent(seq=self._seq, ts=utc_now(), process=slot.unit.name, kind=kind, detail=detail)
        self._events.append(event)
        method = log.warning if kind in {"exited", "unhealthy", "circuit_open", "restarting"} else log.info
        method("process_event", unit=slot.unit.name, kind=kind, detail=detail, restarts=slot.restarts)

    async def _sleep(self, seconds: float) -> bool:
        """Sleep unless stopping; True if the sleep completed."""
        try:
            await asyncio.wait_for(self._stopping.wait(), seconds)
        except TimeoutError:
            return True
        return False

    async def _wait_requires(self, slot: _Slot) -> None:
        for name in slot.unit.requires:
            dep = self._slots.get(name)
            if dep is not None and not dep.ready.is_set():
                self._set(slot, "unknown", f"waiting for {name}")
                await dep.ready.wait()

    async def _run(self, slot: _Slot) -> None:
        await self._wait_requires(slot)
        if isinstance(slot.unit, ExternalUnit):
            await self._run_external(slot)
            return
        while not self._stopping.is_set():
            self._set(slot, "starting", None)
            self._emit(slot, "starting")
            failure: str
            try:
                await slot.unit.start()
            except (UnitError, OSError) as exc:
                failure = str(exc) or type(exc).__name__
            else:
                outcome = await self._monitor(slot)
                if self._stopping.is_set():
                    return
                if outcome == 0 and isinstance(slot.unit, OneShotUnit):
                    self._set(slot, "up", "completed")
                    self._emit(slot, "healthy", "completed")
                    slot.ready.set()
                    slot.settled.set()
                    return
                failure = outcome if isinstance(outcome, str) else f"exit code {outcome}"
                self._emit(slot, "exited", failure)
            delay = slot.policy.record_failure()
            if delay is None:
                self._set(slot, "failed", f"{failure}; restarts stopped after repeated failures")
                self._emit(slot, "circuit_open", failure)
                slot.settled.set()
                slot.manual_restart.clear()
                await slot.manual_restart.wait()
                continue
            slot.restarts += 1
            self._set(slot, "down", failure)
            self._emit(slot, "restarting", f"in {delay:g}s")
            if not await self._sleep(delay):
                return

    async def _monitor(self, slot: _Slot) -> int | str | None:
        """Watch a running process. Returns its exit code, or a reason after killing it."""
        unit, timing = slot.unit, self.timing
        waiter = asyncio.create_task(unit.wait(), name=f"{unit.name}-wait")
        started = time.monotonic()
        healthy = False
        failures = 0
        try:
            while True:
                interval = timing.health_interval_s if healthy else timing.poll_s
                done, _ = await asyncio.wait({waiter}, timeout=interval)
                if done:
                    return waiter.result()
                if self._stopping.is_set():
                    return None
                if isinstance(unit, OneShotUnit):
                    continue
                state = await timed(unit.check, timing.check_timeout_s)
                if state.state in HEALTHY:
                    failures = 0
                    self._set(slot, state.state, state.detail)
                    if not healthy:
                        healthy = True
                        self._emit(slot, "healthy", state.version)
                        slot.ready.set()
                        slot.settled.set()
                    continue
                if not healthy:
                    if time.monotonic() - started > timing.start_timeout_s:
                        await unit.stop(timing.stop_timeout_s)
                        return f"not healthy within {timing.start_timeout_s:g}s ({state.detail})"
                    continue
                failures += 1
                if failures == timing.unhealthy_after:
                    self._set(slot, "degraded", f"health check failing: {state.detail}")
                    self._emit(slot, "unhealthy", state.detail)
                if failures >= timing.restart_unhealthy_after:
                    await unit.stop(timing.stop_timeout_s)
                    return f"unresponsive ({state.detail})"
        finally:
            if not waiter.done():
                waiter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await waiter

    async def _run_external(self, slot: _Slot) -> None:
        healthy = False
        while not self._stopping.is_set():
            state = await timed(slot.unit.check, self.timing.check_timeout_s)
            self._set(slot, state.state, state.detail if state.state != "up" else state.version)
            if state.state in HEALTHY and not healthy:
                healthy = True
                self._emit(slot, "healthy", state.version)
                slot.ready.set()
                slot.settled.set()
            elif state.state not in HEALTHY and healthy:
                healthy = False
                self._emit(slot, "unhealthy", state.detail)
            interval = self.timing.health_interval_s if healthy else self.timing.poll_s * 4
            if not await self._sleep(interval):
                return
