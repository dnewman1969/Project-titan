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
