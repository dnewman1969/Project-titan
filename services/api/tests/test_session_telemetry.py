"""Session telemetry launcher helpers."""

from __future__ import annotations

from uuid import UUID

from titan_api.session_telemetry import fixture_fallback_path, stop_all_session_telemetry


def test_fixture_fallback_ksp() -> None:
    path = fixture_fallback_path("ksp")
    assert path is not None
    assert path.name == "launch-to-orbit.ndjson"


def test_fixture_fallback_unknown_slug() -> None:
    assert fixture_fallback_path("not-a-game") is None


def test_stop_all_session_telemetry_no_op() -> None:
    stop_all_session_telemetry(UUID(int=0))
