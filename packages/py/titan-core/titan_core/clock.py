"""Session monotonic clock (Section 2.1 principle 3, decision D19).

Every event, frame, message and track start carries `t_mono_ns`, the raw value of
`time.perf_counter_ns()` (QueryPerformanceCounter on Windows). A session records its origin
once; `t_session_ms` is milliseconds since that origin (Section 4.1).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def mono_ns() -> int:
    """Current value of the process-independent monotonic clock in nanoseconds."""
    return time.perf_counter_ns()


def utc_now() -> datetime:
    """Current wall-clock time as an aware UTC datetime."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SessionClock:
    """Maps monotonic timestamps onto one session timeline.

    `origin_mono_ns` and `origin_wall` are captured together at session start and stored in
    `sessions.clock_origin_mono_ns` and `sessions.clock_origin_wall`.
    """

    origin_mono_ns: int
    origin_wall: datetime

    def __post_init__(self) -> None:
        if self.origin_wall.tzinfo is None:
            raise ValueError("origin_wall must be timezone-aware")

    @classmethod
    def start(cls) -> SessionClock:
        return cls(origin_mono_ns=mono_ns(), origin_wall=utc_now())

    def t_session_ms(self, t_mono_ns: int | None = None) -> int:
        """Milliseconds since the session origin (floored) for `t_mono_ns`, or for now."""
        t = mono_ns() if t_mono_ns is None else t_mono_ns
        return (t - self.origin_mono_ns) // 1_000_000

    def wall_at(self, t_mono_ns: int) -> datetime:
        """Wall-clock UTC time corresponding to a monotonic timestamp."""
        delta_us = (t_mono_ns - self.origin_mono_ns) // 1_000
        return self.origin_wall.astimezone(UTC) + timedelta(microseconds=delta_us)

    def stamp(self) -> tuple[int, int, datetime]:
        """Return `(t_mono_ns, t_session_ms, wall)` for the current instant."""
        t = mono_ns()
        return t, self.t_session_ms(t), self.wall_at(t)


def recording_t_ms(event_t_mono_ns: int, recording_start_mono_ns: int) -> int:
    """Position of an event on a recording timeline in ms (Section 2.12 sync rule)."""
    return (event_t_mono_ns - recording_start_mono_ns) // 1_000_000
