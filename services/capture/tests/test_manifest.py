"""Recording manifest helpers."""

from pathlib import Path

from titan_core.recording_manifest import (
    append_timeline_event,
    build_manifest,
    default_preset,
    write_manifest,
)


def test_build_and_write_manifest(tmp_path: Path) -> None:
    preset = default_preset()
    body = build_manifest(
        session_id="s-1",
        recording_id="r-1",
        obs_active=False,
        obs_status={"degraded": True},
        preset=preset,
    )
    assert body["version"] == 1
    assert body["preset"]["fps"] == 60
    path = tmp_path / "manifest.json"
    write_manifest(path, body)
    assert path.read_text(encoding="utf-8").startswith("{")
    tl = append_timeline_event(tmp_path, {"kind": "test"})
    assert tl.is_file()
