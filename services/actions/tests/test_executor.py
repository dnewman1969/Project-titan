"""Play executor."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from titan_actions.drivers.hil_driver import HilDriver
from titan_actions.executor import PlayExecutor


def test_execute_ksp_throttle_writes_outcome_log(tmp_path: Path) -> None:
    executor = PlayExecutor(
        session_id=UUID(int=2),
        data_dir=tmp_path,
        driver=HilDriver(session_id=UUID(int=2), trace_path=None, trace=False),
    )
    ok, err, latency_ms = executor.execute("ksp.throttle", {"throttle": 0.5})
    assert ok
    assert err is None
    assert latency_ms >= 0
    path = tmp_path / "play.ndjson"
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["ok"] is True
    assert row["action_id"] == "ksp.throttle"
    assert "latency_ms" in row


def test_unknown_action_returns_error() -> None:
    executor = PlayExecutor(
        session_id=UUID(int=3),
        driver=HilDriver(session_id=UUID(int=3), trace_path=None, trace=False),
    )
    ok, err, latency_ms = executor.execute("unknown.action", {})
    assert not ok
    assert err is not None
    assert latency_ms >= 0


def test_driver_exception_is_surfaced() -> None:
    class Boom:
        def execute(self, action_id: str, params: dict[str, object]) -> tuple[bool, str | None]:
            raise RuntimeError(f"boom:{action_id}")

    executor = PlayExecutor(session_id=UUID(int=9), driver=Boom())  # type: ignore[arg-type]
    ok, err, _latency = executor.execute("ksp.throttle", {})
    assert not ok
    assert err is not None
    assert "boom" in err


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="SCS real input needs Windows")
def test_scs_brake_on_windows() -> None:
    """Optional Windows-real path; cloud coverage lives in test_scs_driver.py mocks."""
    from titan_actions.drivers.scs_driver import ScsDriver

    executor = PlayExecutor(session_id=UUID(int=4), data_dir=None, driver=ScsDriver())
    ok, err, _latency = executor.execute("scs.brake", {"brake": 0.2})
    if not ok:
        pytest.skip(err or "SCS input unavailable on this host")
    assert ok and err is None
