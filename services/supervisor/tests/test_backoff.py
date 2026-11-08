from __future__ import annotations

from titan_supervisor.backoff import RestartPolicy


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ladder_is_1_2_4_8_then_circuit_opens_on_the_fifth_failure() -> None:
    policy = RestartPolicy(clock=Clock())
    assert [policy.record_failure() for _ in range(5)] == [1.0, 2.0, 4.0, 8.0, None]


def test_delay_is_capped_at_30_seconds() -> None:
    policy = RestartPolicy(max_failures=100, clock=Clock())
    delays = [policy.record_failure() for _ in range(8)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_failures_older_than_two_minutes_are_forgotten() -> None:
    clock = Clock()
    policy = RestartPolicy(clock=clock)
    for _ in range(4):
        policy.record_failure()
        clock.now += 10
    assert policy.failures_in_window == 4
    clock.now += 121
    assert policy.failures_in_window == 0
    assert policy.record_failure() == 1.0


def test_four_failures_spread_over_more_than_two_minutes_never_open_the_circuit() -> None:
    clock = Clock()
    policy = RestartPolicy(clock=clock)
    for _ in range(20):
        assert policy.record_failure() is not None
        clock.now += 31
    assert policy.failures_in_window <= 4


def test_reset_closes_the_circuit() -> None:
    policy = RestartPolicy(clock=Clock())
    for _ in range(5):
        policy.record_failure()
    policy.reset()
    assert policy.record_failure() == 1.0
