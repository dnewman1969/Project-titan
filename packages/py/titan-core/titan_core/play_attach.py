"""Resolve which play backend to attach and probe readiness (kRPC / SCS / HIL).

Shared by titan-api (session start / readiness) and titan-actions (PlayExecutor).
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PlayBackend = Literal["auto", "krpc", "scs", "hil", "keyboard"]
SessionSource = Literal["live", "fixture"]


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


def probe_krpc(*, host: str, rpc_port: int, stream_port: int, timeout_s: float = 0.4) -> PlayAttach:
    detail: dict[str, Any] = {"host": host, "rpc_port": rpc_port, "stream_port": stream_port}
    try:
        with socket.create_connection((host, rpc_port), timeout=timeout_s):
            pass
    except OSError as exc:
        return PlayAttach(
            source="live",
            backend="krpc",
            ready=False,
            message=(
                f"kRPC not reachable at {host}:{rpc_port} "
                f"(start KSP with the kRPC mod; stream port {stream_port}). {exc}"
            ),
            detail={**detail, "error": str(exc)},
        )
    return PlayAttach(
        source="live",
        backend="krpc",
        ready=True,
        message=f"kRPC RPC port open at {host}:{rpc_port} - play will attach when a vessel is active.",
        detail=detail,
    )


def probe_scs() -> PlayAttach:
    platform_tag = sys.platform
    if platform_tag != "win32":
        return PlayAttach(
            source="live",
            backend="scs",
            ready=False,
            message="SCS play needs Windows (ViGEm or keyboard). Use fixture/HIL on this host.",
            detail={"platform": platform_tag},
        )
    # Do not import vgamepad here (input libs are titan-actions-only); ScsDriver probes at execute.
    return PlayAttach(
        source="live",
        backend="scs",
        ready=True,
        message=(
            "SCS attach ready on Windows (ViGEm preferred; keyboard brake fallback). "
            "Keep the truck sim focused while agents play."
        ),
        detail={"platform": "win32"},
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
        return probe_krpc(host=host, rpc_port=rpc_port, stream_port=stream_port)
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
