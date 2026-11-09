"""Demo fixture replay launcher."""

from __future__ import annotations

from uuid import UUID

import pytest

from titan_api import demo_replay


def test_ksp_fixture_path_exists() -> None:
    path = demo_replay.ksp_fixture_path()
    assert path.is_file()


def test_stop_demo_replay_missing_session() -> None:
    demo_replay.stop_demo_replay(UUID(int=99))


@pytest.mark.asyncio
async def test_start_demo_replay_default_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []
    sid = UUID("00000000-0000-0000-0000-000000000002")

    class FakeProc:
        pid = 42
        returncode = None
        stderr = None

        async def wait(self) -> int:
            return 0

    async def fake_exec(*args: object, **kwargs: object) -> FakeProc:
        captured.append([str(a) for a in args])
        return FakeProc()

    monkeypatch.setattr(demo_replay.asyncio, "create_subprocess_exec", fake_exec)
    await demo_replay.start_demo_replay(sid)
    assert captured
    argv = captured[0]
    speed_idx = argv.index("--speed") + 1
    assert argv[speed_idx] == "2"
