"""Play executor."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from titan_actions.executor import PlayExecutor


def test_execute_ksp_throttle_writes_log(tmp_path: Path) -> None:
    executor = PlayExecutor(session_id=UUID(int=2), data_dir=tmp_path)
    ok, err = executor.execute("ksp.throttle", {"throttle": 0.5})
    assert ok
    assert err is None
    assert (tmp_path / "play.ndjson").is_file()


def test_unknown_action_returns_error() -> None:
    executor = PlayExecutor(session_id=UUID(int=3), data_dir=None)
    ok, err = executor.execute("unknown.action", {})
    assert not ok
    assert err is not None


def test_scs_brake_ok() -> None:
    executor = PlayExecutor(session_id=UUID(int=4), data_dir=None)
    ok, err = executor.execute("scs.brake", {"brake": 1.0})
    assert ok
    assert err is None
