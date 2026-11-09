"""HIL play driver."""

from __future__ import annotations

from uuid import UUID

from titan_actions.drivers.hil_driver import HilDriver, hil_state
from titan_actions.executor import PlayExecutor


def test_hil_ksp_throttle_and_stage() -> None:
    driver = HilDriver(session_id=UUID(int=1), trace_path=None, trace=False)
    ok, err = driver.execute("ksp.throttle", {"throttle": 0.6})
    assert ok and err is None
    ok, err = driver.execute("ksp.stage", {})
    assert ok and err is None
    state = hil_state()
    assert state["ksp"]["throttle"] == 0.6
    assert state["ksp"]["stage_count"] == 1


def test_executor_uses_injected_hil_driver() -> None:
    driver = HilDriver(session_id=UUID(int=2), trace_path=None, trace=False)
    ex = PlayExecutor(session_id=UUID(int=2), driver=driver)
    ok, err, _latency = ex.execute("scs.brake", {"fraction": 0.8})
    assert ok and err is None
    assert hil_state()["scs"]["brake"] == 0.8
