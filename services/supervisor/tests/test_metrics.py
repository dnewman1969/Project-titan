from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from titan_core.protocol.ws import SystemMetrics
from titan_supervisor.metrics import (
    FrameWindow,
    MetricsSampler,
    NvmlSampler,
    PresentMonTracker,
    find_presentmon,
    frametime_column,
    presentmon_argv,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_frametime_column_handles_presentmon_1_and_2_headers() -> None:
    v1 = "Application,ProcessID,SwapChainAddress,Runtime,SyncInterval,PresentFlags,MsBetweenPresents"
    assert frametime_column(v1) == 6
    v2 = "Application,ProcessID,PresentRuntime,FrameTime,CPUBusy,GPUTime"
    assert frametime_column(v2) == 3
    assert frametime_column("garbage") is None


def test_frame_window_fps_and_p99() -> None:
    clock = Clock()
    window = FrameWindow(window_s=2.0, clock=clock)
    assert window.stats() == (None, None)
    for _ in range(99):
        window.add(10.0)
    window.add(50.0)
    fps, p99 = window.stats()
    assert fps == pytest.approx(1000 * 100 / (99 * 10 + 50), abs=0.1)
    assert p99 == 10.0
    window.add(float("nan"))
    window.add(-1)
    clock.now += 2.5
    assert window.stats() == (None, None)


def test_presentmon_argv_tracks_one_pid() -> None:
    argv = presentmon_argv(Path("PresentMon.exe"), 4242)
    assert argv[argv.index("--process_id") + 1] == "4242"
    assert "--output_stdout" in argv
    assert "--terminate_on_proc_exit" in argv
    assert "--stop_existing_session" in argv


def test_find_presentmon(tmp_path: Path) -> None:
    folder = tmp_path / "third_party" / "cache" / "presentmon"
    folder.mkdir(parents=True)
    exe = folder / "PresentMon-2.6.0-x64.exe"
    exe.write_bytes(b"")
    assert find_presentmon(None, tmp_path, platform="win32") == exe
    assert find_presentmon(str(exe), None, platform="linux") == exe
    assert find_presentmon(str(tmp_path / "missing.exe"), None) is None
    assert find_presentmon(None, tmp_path, platform="linux") is None


@pytest.mark.skipif(sys.platform == "win32", reason="the fake PresentMon is a POSIX script")
async def test_presentmon_tracker_reads_frames(tmp_path: Path) -> None:
    fake = tmp_path / "PresentMon"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import time
            print("Application,ProcessID,MsBetweenPresents", flush=True)
            for _ in range(30):
                print("game.exe,1,16.6667", flush=True)
            time.sleep(30)
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    tracker = PresentMonTracker(fake)
    await tracker.track(os.getpid())
    try:
        for _ in range(100):
            if tracker.stats()[0] is not None:
                break
            await asyncio.sleep(0.05)
        fps, p99 = tracker.stats()
        assert fps == pytest.approx(60.0, abs=0.1)
        assert p99 == pytest.approx(16.67, abs=0.01)
    finally:
        await tracker.close()


async def test_presentmon_missing_means_fps_na() -> None:
    tracker = PresentMonTracker(None)
    await tracker.track(os.getpid())
    assert tracker.stats() == (None, None)
    await tracker.track(None)
    assert tracker.pid is None


class FakeNvml:
    def __init__(self, fail_init: bool = False) -> None:
        self.fail_init = fail_init
        self.shutdown = False

    def nvmlInit(self) -> None:
        if self.fail_init:
            raise RuntimeError("NVML Shared Library Not Found")

    def nvmlDeviceGetCount(self) -> int:
        return 1

    def nvmlDeviceGetHandleByIndex(self, index: int) -> str:
        return f"gpu{index}"

    def nvmlDeviceGetName(self, handle: str) -> bytes:
        return b"NVIDIA GeForce RTX 4070"

    def nvmlDeviceGetUtilizationRates(self, handle: str) -> Any:
        return SimpleNamespace(gpu=81, memory=40)

    def nvmlDeviceGetMemoryInfo(self, handle: str) -> Any:
        return SimpleNamespace(used=9850 * 2**20, total=12282 * 2**20)

    def nvmlDeviceGetTemperature(self, handle: str, sensor: int) -> int:
        return 67

    def nvmlDeviceGetEncoderUtilization(self, handle: str) -> list[int]:
        raise RuntimeError("Not Supported")

    def nvmlShutdown(self) -> None:
        self.shutdown = True


def test_nvml_sampler_maps_fields() -> None:
    nvml = FakeNvml()
    sampler = NvmlSampler(nvml=nvml)
    [gpu] = sampler.sample()
    assert gpu.name == "NVIDIA GeForce RTX 4070"
    assert gpu.util_pct == 81
    assert gpu.vram_used_mb == 9850
    assert gpu.vram_total_mb == 12282
    assert gpu.temp_c == 67
    assert gpu.encoder_util_pct is None
    sampler.close()
    assert nvml.shutdown


def test_nvml_unavailable_means_no_gpus() -> None:
    assert NvmlSampler(nvml=FakeNvml(fail_init=True)).sample() == []
    assert NvmlSampler(enabled=False).sample() == []


async def test_sampler_publishes_at_the_configured_rate() -> None:
    sampler = MetricsSampler(PresentMonTracker(None), NvmlSampler(nvml=FakeNvml()), hz=20)
    published: list[SystemMetrics] = []
    stop = asyncio.Event()

    async def publish(metrics: SystemMetrics) -> None:
        published.append(metrics)
        if len(published) == 2:
            raise ConnectionError("redis restarting")
        if len(published) >= 5:
            stop.set()

    await asyncio.wait_for(sampler.run(publish, stop), 5)
    assert len(published) == 5
    sample = published[-1]
    assert sample.game_fps is None
    assert 0 <= sample.cpu_pct <= 100 * (os.cpu_count() or 1)
    assert 0 < sample.ram_used_mb <= sample.ram_total_mb
    assert sample.gpu[0].name.startswith("NVIDIA")
    assert sample.resource_guard_level == "L0"
    assert sampler.latest == sample
    await sampler.close()
