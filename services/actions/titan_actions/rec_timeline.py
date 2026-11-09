"""Append play events to session recording timeline when REC is active."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from titan_core.clock import utc_now
from titan_core.recording_manifest import append_timeline_event


def append_play_event(
    session_data_dir: str | None,
    *,
    action_id: str,
    ok: bool,
    err: str | None,
    params: dict[str, Any],
) -> None:
    if not session_data_dir:
        return
    root = Path(session_data_dir) / "recording"
    if not (root / "manifest.json").is_file():
        return
    append_timeline_event(
        root,
        {
            "t": utc_now().isoformat(),
            "kind": "play.action",
            "action_id": action_id,
            "ok": ok,
            "error": err,
            "params": params,
        },
    )
