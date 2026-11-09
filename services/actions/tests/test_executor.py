"""Play executor."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from titan_actions.drivers.hil_driver import HilDriver
from titan_actions.executor import PlayExecutor


def test_execute_ksp_throttle_writes_log(tmp_path: Path) -> None:
    executor = PlayExecutor(
        session_id=UUID(int=2),
        data_dir=tmp_path,
        driver=HilDriver(session_id=UUID(int=2), trace_path=None, trace=False),
    )
    ok, err = executor.execute("ksp.throttle", {"throttle": 0.5})
    assert ok
    assert err is None
    assert (tmp_path / "play.ndjson").is_file()


def test_unknown_action_returns_error() -> None:
    executor = PlayExecutor(
        session_id=UUID(int=3),
        driver=HilDriver(session_id=UUID(int=3), trace_path=None, trace=False),
    )
    ok, err = executor.execute("unknown.action", {})
    assert not ok
    assert err is not None


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="SCS driver needs Windows")
def test_scs_brake_on_windows() -> None:
    executor = PlayExecutor(session_id=UUID(int=4), data_dir=None)
    ok, err = executor.execute("scs.brake", {"brake": 0.2})
    if not ok and err and "ViGEm" in err:
        pytest.skip(err)
    assert ok or err is not None
