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


def test_hil_ksp_fly_holds_heading() -> None:
    driver = HilDriver(session_id=UUID(int=4), trace_path=None, trace=False)
    ok, err = driver.execute(
        "ksp.fly",
        {"throttle": 1.0, "pitch_deg": 80, "heading_deg": 90, "sas": True, "stage": True},
    )
    assert ok and err is None
    state = hil_state()["ksp"]
    assert state["throttle"] == 1.0
    assert state["pitch_deg"] == 80
    assert state["heading_deg"] == 90
    assert state["autopilot"] is True
    assert state["sas"] is False
    assert state["stage_count"] == 1


def test_hil_ksp_steer_and_gear() -> None:
    driver = HilDriver(session_id=UUID(int=3), trace_path=None, trace=False)
    ok, err = driver.execute("ksp.steer", {"pitch": -0.35, "yaw": 0.0})
    assert ok and err is None
    ok, err = driver.execute("ksp.gear", {"deployed": True})
    assert ok and err is None
    state = hil_state()["ksp"]
    assert state["steer"]["pitch"] == -0.35
    assert state["gear"] is True
