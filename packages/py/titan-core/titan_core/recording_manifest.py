"""Session recording manifest.json (M8.T3 subset). Shared by API and capture service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_preset() -> dict[str, Any]:
    return {
        "container": "mkv",
        "video_encoder": "jim_nvenc",
        "resolution": "1920x1080",
        "fps": 60,
        "audio_tracks": {
            "1": "game",
            "2": "microphone",
            "3": "agents",
            "4": "music",
        },
    }


def build_manifest(
    *,
    session_id: str,
    recording_id: str,
    obs_active: bool,
    obs_status: dict[str, Any] | None,
    preset: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "session_id": session_id,
        "recording_id": recording_id,
        "preset": preset or default_preset(),
        "obs": {"connected": obs_active, "status": obs_status or {}},
        "tracks": [],
        "markers": [],
    }


def write_manifest(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")


def append_timeline_event(root_dir: Path, event: dict[str, Any]) -> Path:
    """Append one NDJSON timeline row (Phase 1 REC produces real on-disk artifacts)."""
    root_dir.mkdir(parents=True, exist_ok=True)
    path = root_dir / "timeline.ndjson"
    line = json.dumps(event, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


def read_timeline_events(root_dir: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    """Return the newest timeline rows (oldest→newest within the window)."""
    path = root_dir / "timeline.ndjson"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    if limit <= 0:
        return []
    return rows[-limit:]
