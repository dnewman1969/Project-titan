from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from titan_core import clock

ORIGIN_WALL = datetime(2026, 11, 8, 19, 30, tzinfo=UTC)


def test_mono_ns_is_monotonic() -> None:
    samples = [clock.mono_ns() for _ in range(1000)]
    assert samples == sorted(samples)


def test_utc_now_is_aware() -> None:
    assert clock.utc_now().tzinfo is UTC


def test_session_clock_requires_aware_origin() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.SessionClock(origin_mono_ns=0, origin_wall=datetime(2026, 1, 1))


def test_t_session_ms_and_wall_at() -> None:
    c = clock.SessionClock(origin_mono_ns=1_000_000_000, origin_wall=ORIGIN_WALL)
    t = 1_000_000_000 + 84_210_000_000
    assert c.t_session_ms(t) == 84_210
    assert c.wall_at(t) == ORIGIN_WALL + timedelta(seconds=84.21)


def test_wall_at_normalizes_offsets_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    c = clock.SessionClock(origin_mono_ns=0, origin_wall=ORIGIN_WALL.astimezone(plus_two))
    assert c.wall_at(0).tzinfo == UTC
    assert c.wall_at(0) == ORIGIN_WALL


def test_start_and_stamp_are_consistent() -> None:
    c = clock.SessionClock.start()
    t, t_ms, wall = c.stamp()
    assert t >= c.origin_mono_ns
    assert t_ms == (t - c.origin_mono_ns) // 1_000_000
    assert wall >= c.origin_wall
    assert c.t_session_ms() >= t_ms


@given(st.integers(min_value=0, max_value=10**15), st.integers(min_value=0, max_value=10**13))
def test_recording_offsets_floor_to_ms(start: int, delta: int) -> None:
    assert clock.recording_t_ms(start + delta, start) == delta // 1_000_000
