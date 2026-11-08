"""Restart backoff and circuit breaker (Section 2.3): 1 s, 2 s, 4 s ... capped at 30 s; the circuit
opens on the fifth failure within two minutes and stays open until a manual restart."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RestartPolicy:
    initial_s: float = 1.0
    max_s: float = 30.0
    max_failures: int = 5
    window_s: float = 120.0
    clock: Callable[[], float] = time.monotonic
    _failures: deque[float] = field(default_factory=deque, init=False, repr=False)

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] > self.window_s:
            self._failures.popleft()

    @property
    def failures_in_window(self) -> int:
        self._prune(self.clock())
        return len(self._failures)

    def record_failure(self) -> float | None:
        """Record one failure. Returns the delay before the next start, or None when the circuit opens."""
        now = self.clock()
        self._failures.append(now)
        self._prune(now)
        count = len(self._failures)
        if count >= self.max_failures:
            return None
        return float(min(self.max_s, self.initial_s * 2 ** (count - 1)))

    def reset(self) -> None:
        self._failures.clear()
