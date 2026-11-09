"""Play backend settings from environment (session launcher + HIL)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

PlayBackend = Literal["auto", "krpc", "scs", "hil", "keyboard"]


@dataclass(frozen=True)
class PlaySettings:
    backend: PlayBackend
    game_slug: str
    krpc_host: str
    krpc_rpc_port: int
    krpc_stream_port: int
    hil_trace: bool

    @classmethod
    def from_environ(cls) -> PlaySettings:
        raw_backend = os.environ.get("TITAN_PLAY_BACKEND", "auto").strip().lower()
        backend: PlayBackend = "auto"
        if raw_backend in {"auto", "krpc", "scs", "hil", "keyboard"}:
            backend = raw_backend  # type: ignore[assignment]
        if os.environ.get("TITAN_PLAY_HIL", "").strip() in {"1", "true", "yes"}:
            backend = "hil"
        return cls(
            backend=backend,
            game_slug=os.environ.get("TITAN_GAME_SLUG", "ksp").strip().lower() or "ksp",
            krpc_host=os.environ.get("TITAN_KRPC_HOST", "127.0.0.1"),
            krpc_rpc_port=int(os.environ.get("TITAN_KRPC_RPC_PORT", "50000")),
            krpc_stream_port=int(os.environ.get("TITAN_KRPC_STREAM_PORT", "50001")),
            hil_trace=os.environ.get("TITAN_PLAY_HIL_TRACE", "").strip() in {"1", "true", "yes"},
        )
