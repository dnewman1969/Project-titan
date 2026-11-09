"""GPU contention degradation ladder (Section 2.9.4)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from titan_core.protocol.ws import GpuMetrics, ResourceGuardLevel, SystemMetrics

HYSTERESIS_S = 30.0
TRIGGER_S = 10.0
FPS_WINDOW_S = 5.0


@dataclass
class ResourceGuard:
    baseline_fps: float | None = None
    baseline_window_s: float = 60.0
    level: ResourceGuardLevel = "L0"
    game_priority_max: bool = False
    _session_started_at: float | None = None
    _fps_samples: list[tuple[float, float]] = field(default_factory=list)
    _candidate_level: ResourceGuardLevel | None = None
    _candidate_since: float | None = None

    def reset(self) -> None:
        self.baseline_fps = None
        self.level = "L0"
        self._session_started_at = None
        self._fps_samples.clear()
        self._candidate_level = None
        self._candidate_since = None

    def set_session_live(self, live: bool, *, now: float | None = None) -> None:
        clock = now if now is not None else time.monotonic()
        if live and self._session_started_at is None:
            self._session_started_at = clock
        if not live:
            self.reset()

    def set_game_priority_max(self, enabled: bool) -> None:
        self.game_priority_max = enabled
        if enabled:
            self._apply_level("L4", time.monotonic())

    def update(self, sample: SystemMetrics, *, now: float | None = None) -> ResourceGuardLevel:
        clock = now if now is not None else time.monotonic()
        if self.game_priority_max:
            return self.level
        fps_avg = self._fps_avg(sample.game_fps, clock)
        if (
            self._session_started_at is not None
            and self.baseline_fps is None
            and clock - self._session_started_at >= self.baseline_window_s
            and fps_avg is not None
        ):
            self.baseline_fps = fps_avg
        target = self._target_level(fps_avg, self._vram_free_mb(sample.gpu), clock)
        return self._apply_level(target, clock)

    def _fps_avg(self, fps: float | None, clock: float) -> float | None:
        if fps is not None and fps > 0:
            self._fps_samples.append((clock, fps))
        cutoff = clock - FPS_WINDOW_S
        self._fps_samples = [(ts, value) for ts, value in self._fps_samples if ts >= cutoff]
        if not self._fps_samples:
            return None
        return sum(v for _, v in self._fps_samples) / len(self._fps_samples)

    @staticmethod
    def _vram_free_mb(gpus: list[GpuMetrics]) -> float | None:
        if not gpus:
            return None
        gpu = gpus[0]
        if gpu.vram_total_mb is None or gpu.vram_used_mb is None:
            return None
        return float(gpu.vram_total_mb - gpu.vram_used_mb)

    def _target_level(
        self, fps_avg: float | None, vram_free_mb: float | None, clock: float
    ) -> ResourceGuardLevel:
        if self.baseline_fps is None or fps_avg is None:
            return "L0"
        ratio = fps_avg / self.baseline_fps
        if ratio < 0.70 or (vram_free_mb is not None and vram_free_mb < 500):
            return "L3"
        if ratio < 0.80:
            return "L2"
        if ratio < 0.90 or (vram_free_mb is not None and vram_free_mb < 1000):
            return "L1"
        return "L0"

    def _apply_level(self, target: ResourceGuardLevel, clock: float) -> ResourceGuardLevel:
        severity = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
        if target == self.level:
            self._candidate_level = None
            self._candidate_since = None
            return self.level
        if severity[target] < severity[self.level]:
            if self._candidate_level != target:
                self._candidate_level = target
                self._candidate_since = clock
            elif self._candidate_since is not None and clock - self._candidate_since >= HYSTERESIS_S:
                self.level = target
                self._candidate_level = None
                self._candidate_since = None
            return self.level
        if self._candidate_level != target:
            self._candidate_level = target
            self._candidate_since = clock
        elif self._candidate_since is not None and clock - self._candidate_since >= TRIGGER_S:
            self.level = target
        return self.level
