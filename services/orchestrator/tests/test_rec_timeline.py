"""Orchestrator REC timeline hooks."""

from __future__ import annotations

import json
from pathlib import Path

from titan_core.recording_manifest import write_manifest
from titan_orchestrator.rec_timeline import append_rec_timeline


def test_append_rec_timeline_when_manifest_exists(monkeypatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    rec = session_dir / "recording"
    write_manifest(rec / "manifest.json", {"version": 1})
    monkeypatch.setenv("TITAN_SESSION_DATA_DIR", str(session_dir))
    append_rec_timeline(kind="lesson.feedback", payload={"ok": True, "text": "test"})
    line = (rec / "timeline.ndjson").read_text(encoding="utf-8").strip()
    data = json.loads(line)
    assert data["kind"] == "lesson.feedback"
    assert data["ok"] is True
