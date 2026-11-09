"""Select play driver from settings."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from titan_actions.drivers.hil_driver import HilDriver
from titan_actions.drivers.krpc_driver import KrpcDriver
from titan_actions.drivers.protocol import PlayDriver
from titan_actions.drivers.scs_driver import ScsDriver
from titan_actions.play_env import PlaySettings


def build_driver(settings: PlaySettings, *, session_id: UUID, data_dir: Path | None) -> PlayDriver:
    if settings.backend == "hil":
        trace = settings.hil_trace or data_dir is not None
        path = (data_dir / "hil.ndjson") if data_dir is not None else None
        return HilDriver(session_id=session_id, trace_path=path, trace=trace)

    slug = settings.game_slug
    if settings.backend == "krpc" or (settings.backend == "auto" and slug == "ksp"):
        return KrpcDriver(
            host=settings.krpc_host,
            rpc_port=settings.krpc_rpc_port,
            stream_port=settings.krpc_stream_port,
        )
    if settings.backend in {"scs", "keyboard"} or (settings.backend == "auto" and slug in {"ets2", "ats"}):
        return ScsDriver(prefer_keyboard=settings.backend == "keyboard")

    return KrpcDriver(
        host=settings.krpc_host,
        rpc_port=settings.krpc_rpc_port,
        stream_port=settings.krpc_stream_port,
    )
