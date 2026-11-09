"""Re-export play attach helpers; prefer titan_core.play_attach for new code."""

from __future__ import annotations

from titan_actions.play_env import PlaySettings
from titan_core.play_attach import (
    PlayAttach,
    PlayBackend,
    SessionSource,
    probe_attach as _probe_attach,
    probe_hil,
    probe_krpc,
    probe_scs,
    resolve_backend,
    resolve_session_source,
)

__all__ = [
    "PlayAttach",
    "PlayBackend",
    "SessionSource",
    "probe_attach",
    "probe_hil",
    "probe_krpc",
    "probe_scs",
    "resolve_backend",
    "resolve_session_source",
]


def probe_attach(
    *,
    game_slug: str,
    source: SessionSource,
    settings: PlaySettings | None = None,
) -> PlayAttach:
    cfg = settings or PlaySettings.from_environ()
    return _probe_attach(
        game_slug=game_slug,
        source=source,
        krpc_host=cfg.krpc_host,
        krpc_rpc_port=cfg.krpc_rpc_port,
        krpc_stream_port=cfg.krpc_stream_port,
    )
