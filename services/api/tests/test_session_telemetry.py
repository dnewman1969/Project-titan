"""Session telemetry launcher helpers."""

from __future__ import annotations

from uuid import UUID

import pytest

from titan_api import session_telemetry
from titan_api.session_telemetry import fixture_fallback_path, stop_all_session_telemetry


def test_fixture_fallback_ksp() -> None:
    path = fixture_fallback_path("ksp")
    assert path is not None
    assert path.name == "launch-to-orbit.ndjson"


def test_fixture_fallback_unknown_slug() -> None:
    assert fixture_fallback_path("not-a-game") is None


def test_stop_all_session_telemetry_no_op() -> None:
    stop_all_session_telemetry(UUID(int=0))


@pytest.mark.asyncio
async def test_start_live_telemetry_spawns_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []
    sid = UUID("00000000-0000-0000-0000-000000000003")

    class FakeProc:
        pid = 7
        returncode = None
        stderr = None

        async def wait(self) -> int:
            return 0

    async def fake_exec(*args: object, **kwargs: object) -> FakeProc:
        captured.append([str(a) for a in args])
        return FakeProc()

    monkeypatch.setattr(session_telemetry.asyncio, "create_subprocess_exec", fake_exec)
    await session_telemetry.start_live_telemetry(sid, game_slug="ksp", install_path="/games/ksp")
    assert captured
    assert "--install-path" in captured[0]
    assert "/games/ksp" in captured[0]
    await session_telemetry.start_live_telemetry(sid, game_slug="ksp", install_path="/games/ksp")
    assert len(captured) == 1


def test_stop_live_telemetry_terminates(monkeypatch: pytest.MonkeyPatch) -> None:
    sid = UUID("00000000-0000-0000-0000-000000000004")

    class FakeProc:
        returncode = None
        terminated = False

        def terminate(self) -> None:
            self.terminated = True

    proc = FakeProc()
    session_telemetry._LIVE_PROCS[sid] = proc
    session_telemetry.stop_live_telemetry(sid)
    assert proc.terminated
    assert sid not in session_telemetry._LIVE_PROCS
