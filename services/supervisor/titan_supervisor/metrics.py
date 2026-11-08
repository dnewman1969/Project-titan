"""System metrics at 1 Hz into `titan:sys:metrics` (M1.T6, decision D18).

CPU and RAM come from psutil, GPUs from NVML (`nvidia-ml-py`; non-NVIDIA systems report an empty
list, shown as n/a), and game FPS from a PresentMon console process that tracks the game's PID.
PresentMon reads ETW, so it needs administrator rights or membership of the Performance Log Users
group; without them FPS stays n/a and a warning is logged once.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import shutil
import sys
import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import psutil

from titan_core.clock import utc_now
from titan_core.logging import get_logger
from titan_core.protocol.ws import GpuMetrics, SystemMetrics
from titan_supervisor import procutil

log = get_logger(__name__)

PRESENTMON_SESSION = "TitanPresentMon"
FRAME_WINDOW_S = 2.0
_FRAMETIME_COLUMNS = ("msbetweenpresents", "frametime", "msbetweendisplaychange")


def find_presentmon(
    configured: str | None, app_dir: Path | None, platform: str = sys.platform
) -> Path | None:
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    if platform != "win32":
        return None
    for folder in (
        [app_dir / "presentmon", app_dir / "third_party" / "cache" / "presentmon"] if app_dir else []
    ):
        found = sorted(folder.glob("PresentMon*.exe"))
        if found:
            return found[-1]
    which = shutil.which("PresentMon") or shutil.which("PresentMon.exe")
    return Path(which) if which else None


def presentmon_argv(exe: Path, pid: int) -> list[str]:
    return [
        str(exe),
        "--process_id", str(pid),
        "--output_stdout",
        "--no_console_stats",
        "--stop_existing_session",
        "--session_name", PRESENTMON_SESSION,
        "--terminate_on_proc_exit",
        "--v1_metrics",
    ]  # fmt: skip


def frametime_column(header: str) -> int | None:
    """Index of the frame-time column in a PresentMon CSV header (1.x or 2.x metric names)."""
    names = [h.strip().lower() for h in header.split(",")]
    for wanted in _FRAMETIME_COLUMNS:
        if wanted in names:
            return names.index(wanted)
    return None


class FrameWindow:
    """Frame times over the last `window_s` seconds."""

    def __init__(self, window_s: float = FRAME_WINDOW_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.window_s = window_s
        self._clock = clock
        self._frames: deque[tuple[float, float]] = deque()

    def add(self, frametime_ms: float) -> None:
        if frametime_ms > 0 and math.isfinite(frametime_ms):
            self._frames.append((self._clock(), frametime_ms))

    def _recent(self) -> list[float]:
        cutoff = self._clock() - self.window_s
        while self._frames and self._frames[0][0] < cutoff:
            self._frames.popleft()
        return [ft for _, ft in self._frames]

    def clear(self) -> None:
        self._frames.clear()

    def stats(self) -> tuple[float | None, float | None]:
        """`(fps, p99 frame time ms)`, or `(None, None)` without recent frames."""
        frames = self._recent()
        if not frames:
            return None, None
        fps = 1000.0 * len(frames) / sum(frames)
        ordered = sorted(frames)
        p99 = ordered[min(len(ordered) - 1, math.ceil(0.99 * len(ordered)) - 1)]
        return round(fps, 1), round(p99, 2)


class PresentMonTracker:
    def __init__(self, exe: Path | None, window: FrameWindow | None = None) -> None:
        self.exe = exe
        self.window = window or FrameWindow()
        self.pid: int | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._warned = False

    async def track(self, pid: int | None) -> None:
        await self.close()
        self.pid = pid
        self.window.clear()
        if pid is None:
            return
        if self.exe is None:
            if not self._warned:
                log.warning(
                    "presentmon_unavailable", hint="FPS shows n/a; fetch it with tools/fetch-third-party.py"
                )
                self._warned = True
            return
        self._proc = await procutil.spawn(presentmon_argv(self.exe, pid))
        self._reader = asyncio.create_task(self._read(self._proc), name="presentmon")
        log.info("presentmon_tracking", pid=pid)

    async def _read(self, proc: asyncio.subprocess.Process) -> None:
        if proc.stdout is None:
            return
        column: int | None = None
        while line := await proc.stdout.readline():
            text = line.decode("utf-8", errors="replace").strip()
            if column is None:
                column = frametime_column(text)
                continue
            fields = text.split(",")
            if column < len(fields):
                with contextlib.suppress(ValueError):
                    self.window.add(float(fields[column]))
        code = await proc.wait()
        if column is None:
            log.warning(
                "presentmon_exited", code=code, hint="needs admin or Performance Log Users membership"
            )

    def stats(self) -> tuple[float | None, float | None]:
        if self.pid is None or not procutil.pid_alive(self.pid):
            return None, None
        return self.window.stats()

    async def close(self) -> None:
        if self._proc is not None:
            await procutil.terminate_tree(self._proc, 2)
            self._proc = None
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None


class NvmlSampler:
    """NVIDIA GPUs through NVML. Any NVML failure means 'no GPU metrics' rather than an error."""

    def __init__(self, enabled: bool = True, nvml: Any = None) -> None:
        self._nvml = nvml
        self._handles: list[Any] = []
        self.available = False
        if not enabled:
            return
        try:
            if self._nvml is None:
                import pynvml

                self._nvml = pynvml
            self._nvml.nvmlInit()
            count = self._nvml.nvmlDeviceGetCount()
            self._handles = [self._nvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            self.available = True
        except Exception as exc:  # NVMLError subclasses, missing driver DLL, ...
            log.info("nvml_unavailable", reason=type(exc).__name__)

    def _read(self, fn: str, *args: Any) -> Any:
        try:
            return getattr(self._nvml, fn)(*args)
        except Exception:
            return None

    def sample(self) -> list[GpuMetrics]:
        gpus: list[GpuMetrics] = []
        for index, handle in enumerate(self._handles):
            name = self._read("nvmlDeviceGetName", handle)
            util = self._read("nvmlDeviceGetUtilizationRates", handle)
            mem = self._read("nvmlDeviceGetMemoryInfo", handle)
            temp = self._read("nvmlDeviceGetTemperature", handle, 0)  # NVML_TEMPERATURE_GPU
            enc = self._read("nvmlDeviceGetEncoderUtilization", handle)
            gpus.append(
                GpuMetrics(
                    index=index,
                    name=name.decode() if isinstance(name, bytes) else str(name or f"GPU {index}"),
                    util_pct=float(util.gpu) if util is not None else None,
                    vram_used_mb=int(mem.used // 2**20) if mem is not None else None,
                    vram_total_mb=int(mem.total // 2**20) if mem is not None else None,
                    temp_c=float(temp) if temp is not None else None,
                    encoder_util_pct=float(enc[0]) if isinstance(enc, Sequence) and enc else None,
                )
            )
        return gpus

    def close(self) -> None:
        if self.available:
            with contextlib.suppress(Exception):
                self._nvml.nvmlShutdown()
            self.available = False


Publisher = Callable[[SystemMetrics], Awaitable[None]]


class MetricsSampler:
    def __init__(self, presentmon: PresentMonTracker, nvml: NvmlSampler, *, hz: float = 1.0) -> None:
        self.presentmon = presentmon
        self.nvml = nvml
        self.interval_s = 1.0 / hz
        self.latest: SystemMetrics | None = None
        psutil.cpu_percent(None)

    def sample(self) -> SystemMetrics:
        mem = psutil.virtual_memory()
        fps, p99 = self.presentmon.stats()
        return SystemMetrics(
            ts=utc_now(),
            game_fps=fps,
            game_frametime_p99_ms=p99,
            cpu_pct=float(psutil.cpu_percent(None)),
            ram_used_mb=int((mem.total - mem.available) // 2**20),
            ram_total_mb=int(mem.total // 2**20),
            gpu=self.nvml.sample(),
            tokens_per_min=0,
            llm_queue_depth=0,
            goals_active=0,
            tasks_open=0,
            resource_guard_level="L0",
        )

    async def run(self, publish: Publisher, stop: asyncio.Event) -> None:
        failing = False
        while not stop.is_set():
            started = time.monotonic()
            self.latest = self.sample()
            try:
                await publish(self.latest)
            except Exception as exc:  # Redis down or restarting: keep sampling, log once per outage
                if not failing:
                    log.warning("metrics_publish_failed", error=type(exc).__name__)
                failing = True
            else:
                if failing:
                    log.info("metrics_publish_recovered")
                failing = False
            delay = max(0.0, self.interval_s - (time.monotonic() - started))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), delay)

    async def close(self) -> None:
        await self.presentmon.close()
        self.nvml.close()
