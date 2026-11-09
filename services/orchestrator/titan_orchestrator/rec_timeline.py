"""Append learn-and-play rows to session REC timeline when recording."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from titan_core.clock import utc_now
from titan_core.recording_manifest import append_timeline_event


def append_rec_timeline(*, kind: str, payload: dict[str, Any]) -> None:
    data_dir = os.environ.get("TITAN_SESSION_DATA_DIR")
    if not data_dir:
        return
    root = Path(data_dir) / "recording"
    if not (root / "manifest.json").is_file():
        return
    append_timeline_event(root, {"t": utc_now().isoformat(), "kind": kind, **payload})
