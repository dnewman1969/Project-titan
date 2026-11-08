from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from titan_supervisor.core import Supervisor
from titan_supervisor.units import Unit

from .fakes import FAST, FakeExternal, FakeOneShot, FakeProcess, fast_policy


@pytest.fixture
async def make() -> AsyncIterator[Callable[..., Supervisor]]:
    created: list[Supervisor] = []

    def factory(*units: Unit) -> Supervisor:
        supervisor = Supervisor(units, timing=FAST, policy_factory=fast_policy)
        created.append(supervisor)
        return supervisor

    yield factory
    for supervisor in created:
        await supervisor.stop()


async def until(predicate: Callable[[], bool], timeout_s: float = 3.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not predicate():  # noqa: ASYNC110 (polling fakes)
            await asyncio.sleep(0.005)


def state(supervisor: Supervisor, name: str) -> str:
    return next(s.state for s in supervisor.status().services if s.name == name)


def kinds(supervisor: Supervisor, name: str) -> list[str]:
    return [e.kind for e in supervisor.status().events if e.process == name]


async def test_starts_in_order_waiting_for_each_to_be_healthy(make: Callable[..., Supervisor]) -> None:
    log: list[str] = []
    first = FakeProcess("postgres", healthy_after=3, log=log)
    second = FakeProcess("chroma", log=log)
    supervisor = make(first, second)
    await supervisor.start()
    assert log == ["start postgres", "start chroma"]
    assert supervisor.ready
    assert [s.state for s in supervisor.status().services] == ["up", "up"]
    assert kinds(supervisor, "postgres") == ["starting", "healthy"]


async def test_requires_waits_for_the_dependency(make: Callable[..., Supervisor]) -> None:
    db = FakeProcess("postgres", fail_starts=2)
    migrate = FakeOneShot("migrate", requires=["postgres"])
    supervisor = make(migrate, db)
    await supervisor.start()
    await until(lambda: supervisor.ready)
    assert migrate.runs == 1
    assert db.starts == 3
    assert state(supervisor, "migrate") == "up"


async def test_a_crashed_process_is_restarted_and_the_events_are_logged(
    make: Callable[..., Supervisor],
) -> None:
    api = FakeProcess("api")
    supervisor = make(api)
    await supervisor.start()
    first_pid = api.pid
    api.crash()
    await until(lambda: api.starts == 2 and state(supervisor, "api") == "up")
    assert api.pid != first_pid
    services = supervisor.status().services
    assert services[0].restarts == 1
    assert kinds(supervisor, "api") == ["starting", "healthy", "exited", "restarting", "starting", "healthy"]
    restarting = next(e for e in supervisor.status().events if e.kind == "restarting")
    assert restarting.detail == "in 0.01s"


async def test_backoff_doubles_between_failed_starts(make: Callable[..., Supervisor]) -> None:
    api = FakeProcess("api", fail_starts=3)
    supervisor = make(api)
    await supervisor.start()
    await until(lambda: state(supervisor, "api") == "up")
    delays = [e.detail for e in supervisor.status().events if e.kind == "restarting"]
    assert delays == ["in 0.01s", "in 0.02s", "in 0.04s"]


async def test_circuit_opens_after_five_failures_and_manual_restart_closes_it(
    make: Callable[..., Supervisor],
) -> None:
    api = FakeProcess("api", fail_starts=5)
    other = FakeProcess("chroma")
    supervisor = make(api, other)
    await supervisor.start()
    assert state(supervisor, "api") == "failed"
    assert api.starts == 5
    assert "circuit_open" in kinds(supervisor, "api")
    assert state(supervisor, "chroma") == "up", "the start order moves on past a failed unit"
    assert not supervisor.ready
    await asyncio.sleep(0.1)
    assert api.starts == 5, "no restarts while the circuit is open"
    await supervisor.restart("api")
    await until(lambda: state(supervisor, "api") == "up")
    assert api.starts == 6


async def test_not_healthy_within_the_start_timeout_counts_as_a_failure(
    make: Callable[..., Supervisor],
) -> None:
    api = FakeProcess("api", healthy_after=10_000)
    supervisor = Supervisor([api], timing=FAST, policy_factory=fast_policy)
    try:
        task = asyncio.create_task(supervisor.start())
        await until(lambda: "exited" in kinds(supervisor, "api"), timeout_s=3)
        exited = next(e for e in supervisor.status().events if e.kind == "exited")
        assert exited.detail is not None
        assert exited.detail.startswith("not healthy within 1s")
        assert api.stops >= 1
        task.cancel()
    finally:
        await supervisor.stop()


async def test_unhealthy_process_is_degraded_then_restarted(make: Callable[..., Supervisor]) -> None:
    api = FakeProcess("api")
    supervisor = make(api)
    await supervisor.start()
    api.healthy = False
    await until(lambda: state(supervisor, "api") == "degraded")
    assert "unhealthy" in kinds(supervisor, "api")
    await until(lambda: api.starts == 2)
    api.healthy = True
    await until(lambda: state(supervisor, "api") == "up")
    exited = [e for e in supervisor.status().events if e.kind == "exited"]
    assert exited[0].detail == "unresponsive (not answering)"


async def test_external_units_are_only_health_checked(make: Callable[..., Supervisor]) -> None:
    redis = FakeExternal("redis")
    supervisor = make(redis)
    await supervisor.start()
    assert state(supervisor, "redis") == "up"
    assert supervisor.status().services[0].kind == "external"
    redis.up = False
    await until(lambda: state(supervisor, "redis") == "down")
    redis.up = True
    await until(lambda: state(supervisor, "redis") == "up")
    assert kinds(supervisor, "redis") == ["healthy", "unhealthy", "healthy"]


async def test_failed_oneshot_is_retried(make: Callable[..., Supervisor]) -> None:
    migrate = FakeOneShot("migrate", exit_codes=[1, 0])
    supervisor = make(migrate)
    await supervisor.start()
    await until(lambda: state(supervisor, "migrate") == "up")
    assert migrate.runs == 2
    assert next(e.detail for e in supervisor.status().events if e.kind == "exited") == "exit code 1"


async def test_stop_is_in_reverse_order_and_final() -> None:
    log: list[str] = []
    units = [FakeProcess("postgres", log=log), FakeProcess("chroma", log=log), FakeProcess("api", log=log)]
    supervisor = Supervisor(units, timing=FAST, policy_factory=fast_policy)
    await supervisor.start()
    log.clear()
    await supervisor.stop()
    assert log == ["stop api", "stop chroma", "stop postgres"]
    assert [s.state for s in supervisor.status().services] == ["stopped"] * 3
    await asyncio.sleep(0.05)
    assert all(u.starts == 1 for u in units), "nothing restarts after stop"


async def test_events_since(make: Callable[..., Supervisor]) -> None:
    supervisor = make(FakeProcess("api"))
    await supervisor.start()
    events = supervisor.status().events
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert supervisor.events_since(events[0].seq) == events[1:]


def test_duplicate_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        Supervisor([FakeProcess("api"), FakeProcess("api")])
