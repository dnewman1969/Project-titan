"""Recording manifest + timeline helpers."""

from __future__ import annotations

from pathlib import Path

from titan_core.recording_manifest import (
    append_timeline_event,
    build_manifest,
    materialize_stub_tracks,
    read_manifest,
    read_timeline_events,
)


def test_read_timeline_events_returns_newest_window(tmp_path: Path) -> None:
    root = tmp_path / "recording"
    for i in range(5):
        append_timeline_event(
            root, {"t": str(i), "kind": "recording.start" if i == 0 else "play.action", "n": i}
        )
    rows = read_timeline_events(root, limit=3)
    assert [r["n"] for r in rows] == [2, 3, 4]
    assert read_timeline_events(tmp_path / "missing", limit=10) == []


def test_materialize_stub_tracks_writes_files(tmp_path: Path) -> None:
    root = tmp_path / "recording"
    tracks = materialize_stub_tracks(root)
    assert len(tracks) == 4
    assert all(t["source"] == "stub" for t in tracks)
    for track in tracks:
        assert (root / str(track["path"])).is_file()
    manifest = build_manifest(
        session_id="s",
        recording_id="r",
        obs_active=False,
        obs_status={"degraded": True},
        preset=None,
        tracks=tracks,
    )
    path = root / "manifest.json"
    from titan_core.recording_manifest import write_manifest

    write_manifest(path, manifest)
    loaded = read_manifest(path)
    assert loaded is not None
    assert loaded["tracks"][0]["id"] == "gameplay_video"
