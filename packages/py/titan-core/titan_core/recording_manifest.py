"""Session recording manifest.json (M8.T3 subset). Shared by API and capture service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Ops Center Webcam panel track ids (beta stubs until real OBS/FFmpeg lands).
TRACK_SPECS: tuple[tuple[str, str], ...] = (
    ("gameplay_video", "Gameplay video"),
    ("game_audio", "Game audio"),
    ("mic_audio", "Mic audio"),
    ("webcam_video", "Webcam video"),
)


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


def build_track_entries(*, obs_connected: bool, root_dir: Path | None = None) -> list[dict[str, Any]]:
    """Declare per-track capture rows (OBS-backed or on-disk stubs)."""
    source = "obs" if obs_connected else "stub"
    state = "recording" if obs_connected else "stub"
    tracks: list[dict[str, Any]] = []
    for track_id, label in TRACK_SPECS:
        rel = f"tracks/{track_id}.{'mkv' if obs_connected and track_id.endswith('video') else 'stub.txt'}"
        if obs_connected and not track_id.endswith("video"):
            rel = f"tracks/{track_id}.flac"
        entry: dict[str, Any] = {
            "id": track_id,
            "kind": track_id,
            "label": label,
            "source": source,
            "state": state,
            "path": rel,
        }
        if root_dir is not None and source == "stub":
            entry["absolute_path"] = str(root_dir / rel)
        tracks.append(entry)
    return tracks


def materialize_stub_tracks(root_dir: Path) -> list[dict[str, Any]]:
    """Write placeholder track files and return stub track entries for the manifest."""
    tracks_dir = root_dir / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    tracks = build_track_entries(obs_connected=False, root_dir=root_dir)
    for track in tracks:
        path = root_dir / str(track["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"Titan beta stub for {track['label']}. OBS/FFmpeg will replace this with a real media file.\n",
            encoding="utf-8",
        )
    return tracks


def build_manifest(
    *,
    session_id: str,
    recording_id: str,
    obs_active: bool,
    obs_status: dict[str, Any] | None,
    preset: dict[str, Any] | None,
    tracks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "session_id": session_id,
        "recording_id": recording_id,
        "preset": preset or default_preset(),
        "obs": {"connected": obs_active, "status": obs_status or {}},
        "tracks": tracks if tracks is not None else build_track_entries(obs_connected=obs_active),
        "markers": [],
    }


def write_manifest(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")


def read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


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
