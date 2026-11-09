"""Resolve which play backend to attach and probe readiness (kRPC / SCS / HIL).

Shared by titan-api (session start / readiness) and titan-actions (PlayExecutor).
"""

from __future__ import annotations

import errno
import mmap
import os
import socket
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PlayBackend = Literal["auto", "krpc", "scs", "hil", "keyboard"]
SessionSource = Literal["live", "fixture"]

SCS_TELEMETRY_MMAP_BYTES = 512
SCS_TELEMETRY_TAG = "Local\\SCSTelemetry"


@dataclass(frozen=True)
class PlayAttach:
    """How titan-actions should attach for this session."""

    source: SessionSource
    backend: PlayBackend
    ready: bool
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def attach_probe_timeout_s() -> float:
    raw = os.environ.get("TITAN_PLAY_ATTACH_TIMEOUT_S", "0.6")
    try:
        return max(0.05, min(5.0, float(raw)))
    except ValueError:
        return 0.6


def resolve_backend(game_slug: str, *, source: SessionSource) -> PlayBackend:
    """Pick an explicit play backend for a live install or fixture session."""
    if source == "fixture":
        return "hil"
    slug = game_slug.strip().lower()
    if slug == "ksp":
        return "krpc"
    if slug in {"ets2", "ats"}:
        return "scs"
    return "hil"


def resolve_session_source(
    *,
    session_source: str | None,
    demo_telemetry: bool,
    has_install: bool,
) -> SessionSource:
    """Live only when an install is attached and the session is not fixture/demo."""
    if not has_install:
        return "fixture"
    if demo_telemetry or session_source == "fixture":
        return "fixture"
    return "live"


def _friendly_socket_error(exc: OSError) -> str:
    refused = isinstance(exc, ConnectionRefusedError) or exc.errno in {
        errno.ECONNREFUSED,
        10061,  # WSAECONNREFUSED
    }
    if refused:
        return "Nothing is listening on that port yet."
    timed_out = exc.errno in {errno.ETIMEDOUT, 10060, 110}
    if timed_out:
        return "Timed out waiting for the port."
    return str(exc)


def _tcp_port_open(host: str, port: int, *, timeout_s: float) -> tuple[bool, OSError | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
        return True, None
    except OSError as exc:
        return False, exc


def probe_krpc(
    *,
    host: str,
    rpc_port: int,
    stream_port: int,
    timeout_s: float | None = None,
) -> PlayAttach:
    timeout = attach_probe_timeout_s() if timeout_s is None else timeout_s
    detail: dict[str, Any] = {
        "host": host,
        "rpc_port": rpc_port,
        "stream_port": stream_port,
        "timeout_s": timeout,
    }
    rpc_ok, rpc_err = _tcp_port_open(host, rpc_port, timeout_s=timeout)
    if not rpc_ok and rpc_err is not None:
        hint = _friendly_socket_error(rpc_err)
        return PlayAttach(
            source="live",
            backend="krpc",
            ready=False,
            message=(
                f"kRPC is not running — install the kRPC mod in GameData, start KSP, and confirm "
                f"RPC {host}:{rpc_port} and stream {stream_port} are listening. {hint}"
            ),
            detail={**detail, "rpc_reachable": False, "error": str(rpc_err)},
        )
    stream_ok, stream_err = _tcp_port_open(host, stream_port, timeout_s=timeout)
    if not stream_ok and stream_err is not None:
        hint = _friendly_socket_error(stream_err)
        return PlayAttach(
            source="live",
            backend="krpc",
            ready=False,
            message=(
                f"kRPC RPC port is open but the stream port {host}:{stream_port} is not ready. "
                f"Restart KSP/kRPC or check firewall. {hint}"
            ),
            detail={**detail, "rpc_reachable": True, "stream_reachable": False, "error": str(stream_err)},
        )
    return PlayAttach(
        source="live",
        backend="krpc",
        ready=True,
        message=(
            f"kRPC listening on {host}:{rpc_port} (stream {stream_port}). "
            "Load a vessel with an active flight scene for play proposals."
        ),
        detail={**detail, "rpc_reachable": True, "stream_reachable": True},
    )


def _scs_telemetry_shm_open() -> bool:
    if os.name != "nt":
        return False
    try:
        mapping = mmap.mmap(  # type: ignore[call-arg]
            -1,
            SCS_TELEMETRY_MMAP_BYTES,
            tagname=SCS_TELEMETRY_TAG,
            access=mmap.ACCESS_READ,
        )
        mapping.close()
        return True
    except OSError:
        return False


def probe_scs() -> PlayAttach:
    platform_tag = sys.platform
    if platform_tag != "win32" and os.name != "nt":
        return PlayAttach(
            source="live",
            backend="scs",
            ready=False,
            message="SCS live play needs Windows (ViGEm or keyboard). Use fixture/HIL on this host.",
            detail={"platform": platform_tag},
        )
    telemetry = _scs_telemetry_shm_open()
    if not telemetry:
        return PlayAttach(
            source="live",
            backend="scs",
            ready=False,
            message=(
                "SCS telemetry shared memory (Local\\SCSTelemetry) not found. "
                "Start ETS2/ATS with the scs-telemetry plugin installed, then retry."
            ),
            detail={"platform": "win32", "telemetry_shm": False},
        )
    return PlayAttach(
        source="live",
        backend="scs",
        ready=True,
        message=(
            "SCS telemetry active. Play uses ViGEm virtual pad (preferred) or keyboard "
            "W/S throttle/brake — no physical gamepad required; keep the truck sim focused."
        ),
        detail={
            "platform": "win32",
            "telemetry_shm": True,
            "control_modes": ["vgamepad", "keyboard"],
            "physical_pad_required": False,
        },
    )


def probe_hil(*, source: SessionSource = "fixture") -> PlayAttach:
    return PlayAttach(
        source=source,
        backend="hil",
        ready=True,
        message="Software HIL attach - in-memory play only (no game input).",
        detail={"hil": True},
    )


def probe_attach(
    *,
    game_slug: str,
    source: SessionSource,
    krpc_host: str | None = None,
    krpc_rpc_port: int | None = None,
    krpc_stream_port: int | None = None,
    timeout_s: float | None = None,
) -> PlayAttach:
    """Resolve backend and probe whether play can attach now."""
    backend = resolve_backend(game_slug, source=source)
    if backend == "hil":
        return probe_hil(source=source)
    if backend == "krpc":
        host = krpc_host or os.environ.get("TITAN_KRPC_HOST", "127.0.0.1")
        rpc_port = (
            krpc_rpc_port
            if krpc_rpc_port is not None
            else int(os.environ.get("TITAN_KRPC_RPC_PORT", "50000"))
        )
        stream_port = (
            krpc_stream_port
            if krpc_stream_port is not None
            else int(os.environ.get("TITAN_KRPC_STREAM_PORT", "50001"))
        )
        return probe_krpc(host=host, rpc_port=rpc_port, stream_port=stream_port, timeout_s=timeout_s)
    if backend in {"scs", "keyboard"}:
        attach = probe_scs()
        if backend == "keyboard":
            return PlayAttach(
                source=attach.source,
                backend="keyboard",
                ready=attach.ready,
                message=attach.message,
                detail=attach.detail,
            )
        return attach
    return probe_hil(source=source)
