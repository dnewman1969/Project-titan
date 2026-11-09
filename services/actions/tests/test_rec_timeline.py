"""Recording timeline hooks for play."""

from __future__ import annotations

import json
from pathlib import Path

from titan_actions.rec_timeline import append_play_event
from titan_core.recording_manifest import write_manifest


def test_append_play_event_when_recording(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    rec = session_dir / "recording"
    write_manifest(rec / "manifest.json", {"version": 1})
    append_play_event(
        str(session_dir),
        action_id="ksp.throttle",
        ok=True,
        err=None,
        params={"throttle": 0.5},
    )
    line = (rec / "timeline.ndjson").read_text(encoding="utf-8").strip()
    data = json.loads(line)
    assert data["kind"] == "play.action"
    assert data["action_id"] == "ksp.throttle"
