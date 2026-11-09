"""Recording manifest + timeline helpers."""

from __future__ import annotations

from pathlib import Path

from titan_core.recording_manifest import append_timeline_event, read_timeline_events


def test_read_timeline_events_returns_newest_window(tmp_path: Path) -> None:
    root = tmp_path / "recording"
    for i in range(5):
        append_timeline_event(
            root, {"t": str(i), "kind": "recording.start" if i == 0 else "play.action", "n": i}
        )
    rows = read_timeline_events(root, limit=3)
    assert [r["n"] for r in rows] == [2, 3, 4]
    assert read_timeline_events(tmp_path / "missing", limit=10) == []
