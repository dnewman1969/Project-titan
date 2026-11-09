"""`titan-supervisor`: started by Electron with the launch token; starts everything else (Section 2.3).

Exits when told to (`POST /shutdown`, SIGINT/SIGTERM/SIGBREAK) or when the process named by
`TITAN_PARENT_PID` (Electron) is gone, stopping children in reverse start order.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from titan_core.config import TitanConfig, expand_path, find_app_config_dir, load_config
from titan_core.logging import configure_logging, get_logger
from titan_core.protocol.ws import SystemMetrics
from titan_core.secrets import generate_password
from titan_core.streams import SYS_METRICS, SYS_METRICS_MAXLEN, redis_client, xadd_model
from titan_models.resource_guard import ResourceGuard
from titan_supervisor import procutil
from titan_supervisor.catalog import ChildEnv, build_units
from titan_supervisor.core import Supervisor, Timing
from titan_supervisor.metrics import MetricsSampler, NvmlSampler, PresentMonTracker, find_presentmon
from titan_supervisor.server import bind, create_app, embedded_server
from titan_supervisor.winjob import create_job

LAUNCH_TOKEN_ENV = "TITAN_LAUNCH_TOKEN"  # noqa: S105 (variable name)
PARENT_PID_ENV = "TITAN_PARENT_PID"
log = get_logger("titan_supervisor")


def app_dir() -> Path | None:
    """The folder holding `config/` (repo root in development, `resources/` when packaged)."""
    try:
        return find_app_config_dir().parent
    except FileNotFoundError:
        return None


async def watch_parent(pid: int, stop: asyncio.Event, interval_s: float = 1.0) -> None:
    while not stop.is_set():
        if not procutil.pid_alive(pid):
            log.warning("parent_exited", parent_pid=pid)
            stop.set()
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), interval_s)


def install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, request_stop)


async def run(cfg: TitanConfig, *, token: str, parent_pid: int | None, metrics: bool = True) -> int:
    try:
        sock = bind(cfg.supervisor.host, cfg.supervisor.port)
    except OSError as exc:
        log.error("supervisor_port_in_use", port=cfg.supervisor.port, error=str(exc))
        return 2
    stop = asyncio.Event()
    install_signal_handlers(stop)
    folder = app_dir()
    supervisor = Supervisor(
        build_units(cfg, app_dir=folder, env=ChildEnv(cfg)),
        timing=Timing(start_timeout_s=cfg.supervisor.start_timeout_s),
    )
    sampler = (
        MetricsSampler(
            PresentMonTracker(find_presentmon(cfg.metrics.presentmon_path, folder)),
            NvmlSampler(cfg.metrics.nvml),
            hz=cfg.metrics.sample_hz,
        )
        if metrics
        else None
    )
    server = embedded_server(create_app(supervisor, token=token, sampler=sampler, on_shutdown=stop.set))
    server_task = asyncio.create_task(server.serve(sockets=[sock]), name="http")
    tasks = [asyncio.create_task(supervisor.start(), name="start")]
    if parent_pid is not None:
        tasks.append(asyncio.create_task(watch_parent(parent_pid, stop), name="parent"))
    redis = redis_client(cfg.redis)
    if sampler is not None:
        guard = ResourceGuard()

        async def publish(sample: SystemMetrics) -> None:
            level = guard.update(sample)
            enriched = sample.model_copy(update={"resource_guard_level": level})
            await xadd_model(redis, SYS_METRICS, enriched, maxlen=SYS_METRICS_MAXLEN)

        tasks.append(asyncio.create_task(sampler.run(publish, stop), name="metrics"))
    log.info("supervisor_listening", port=cfg.supervisor.port, processes=supervisor.names)
    await stop.wait()
    log.info("supervisor_stopping")
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await supervisor.stop()
    if sampler is not None:
        await sampler.close()
    await redis.aclose()
    server.should_exit = True
    await server_task
    leftovers = procutil.sweep_descendants()
    if leftovers:
        log.warning("descendants_swept", count=leftovers)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="titan-supervisor", description="Titan process supervisor")
    parser.add_argument("--no-metrics", action="store_true", help="do not sample or publish system metrics")
    args = parser.parse_args(argv)

    cfg = load_config()
    configure_logging(
        "titan-supervisor", level=cfg.logging.level, log_dir=expand_path("%LOCALAPPDATA%/Titan/logs")
    )
    token = os.environ.get(LAUNCH_TOKEN_ENV)
    if not token:
        token = generate_password()
        os.environ[LAUNCH_TOKEN_ENV] = token
        log.warning(
            "launch_token_generated", hint=f"started without {LAUNCH_TOKEN_ENV}; Electron always sets it"
        )
    parent = os.environ.get(PARENT_PID_ENV)
    job = create_job()
    if job is not None:
        job.assign_current_process()
    try:
        return asyncio.run(
            run(cfg, token=token, parent_pid=int(parent) if parent else None, metrics=not args.no_metrics)
        )
    finally:
        if job is not None:
            job.close()


if __name__ == "__main__":
    sys.exit(main())
