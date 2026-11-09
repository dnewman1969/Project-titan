from __future__ import annotations

from datetime import UTC, datetime

from titan_core.protocol.ws import GpuMetrics, SystemMetrics
from titan_models.resource_guard import ResourceGuard


def _sample(fps: float, *, vram_free: int = 2000) -> SystemMetrics:
    return SystemMetrics(
        ts=datetime.now(tz=UTC),
        game_fps=fps,
        game_frametime_p99_ms=10.0,
        cpu_pct=12.0,
        ram_used_mb=1000,
        ram_total_mb=16000,
        gpu=[
            GpuMetrics(
                index=0,
                name="gpu",
                util_pct=10,
                vram_used_mb=10_000,
                vram_total_mb=10_000 + vram_free,
                temp_c=None,
                encoder_util_pct=None,
            )
        ],
        tokens_per_min=0,
        llm_queue_depth=0,
        goals_active=0,
        tasks_open=0,
        resource_guard_level="L0",
    )


def test_guard_escalates_and_recovers_with_hysteresis() -> None:
    guard = ResourceGuard()
    guard.set_session_live(True, now=0.0)
    guard.update(_sample(60.0), now=0.0)
    guard.update(_sample(60.0), now=55.0)
    guard.update(_sample(60.0), now=61.0)
    assert guard.baseline_fps == 60.0
    for tick in range(62, 81):
        guard.update(_sample(53.0), now=float(tick))
    assert guard.update(_sample(53.0), now=81.0) == "L1"
    for tick in range(82, 102):
        guard.update(_sample(47.0), now=float(tick))
    assert guard.update(_sample(47.0), now=102.0) == "L2"
    for tick in range(103, 123):
        guard.update(_sample(40.0), now=float(tick))
    assert guard.update(_sample(40.0), now=123.0) == "L3"
    for tick in range(124, 134):
        guard.update(_sample(60.0), now=float(tick))
    assert guard.level == "L3"
    for tick in range(134, 164):
        guard.update(_sample(60.0), now=float(tick))
    assert guard.update(_sample(60.0), now=164.0) == "L0"
