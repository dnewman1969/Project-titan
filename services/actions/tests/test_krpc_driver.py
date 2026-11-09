"""kRPC driver (mocked connection — no live KSP)."""

from __future__ import annotations

from typing import Any

import pytest

from titan_actions.drivers import krpc_driver
from titan_actions.drivers.krpc_driver import KrpcDriver


class _Control:
    throttle: float = 0.0
    sas: bool = False
    rcs: bool = False
    brakes: bool = False
    gear: bool = False
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    staged: int = 0

    def activate_next_stage(self) -> None:
        self.staged += 1


class _Vessel:
    def __init__(self) -> None:
        self.control = _Control()


class _SpaceCenter:
    active_vessel = _Vessel()


class _Conn:
    space_center = _SpaceCenter()


@pytest.fixture(autouse=True)
def _reset_krpc_conn() -> None:
    krpc_driver._CONN = None
    krpc_driver._CONN_KEY = None
    _Conn.space_center.active_vessel = _Vessel()
    if hasattr(_Conn.space_center, "SASMode"):
        delattr(_Conn.space_center, "SASMode")


def _driver() -> KrpcDriver:
    return KrpcDriver(
        host="127.0.0.1",
        rpc_port=50000,
        stream_port=50001,
        connect_fn=lambda *_a, **_k: _Conn(),
    )


def test_krpc_throttle_and_stage() -> None:
    driver = _driver()
    ok, err = driver.execute("ksp.throttle", {"throttle": 0.8})
    assert ok and err is None
    vessel = _Conn.space_center.active_vessel
    assert vessel.control.throttle == 0.8
    ok, err = driver.execute("ksp.stage", {})
    assert ok and vessel.control.staged == 1


def test_krpc_steer_pitch_yaw_roll() -> None:
    driver = _driver()
    ok, err = driver.execute("ksp.steer", {"pitch": -0.4, "yaw": 0.1, "roll": 0.0})
    assert ok and err is None
    control = _Conn.space_center.active_vessel.control
    assert control.pitch == -0.4
    assert control.yaw == 0.1
    assert control.roll == 0.0

    ok, err = driver.execute("ksp.pitch", {"value": 0.5})
    assert ok and control.pitch == 0.5
    ok, err = driver.execute("ksp.yaw", {"yaw": -0.25})
    assert ok and control.yaw == -0.25
    ok, err = driver.execute("ksp.roll", {"roll": 0.75})
    assert ok and control.roll == 0.75


def test_krpc_steer_requires_axis() -> None:
    ok, err = _driver().execute("ksp.steer", {})
    assert not ok
    assert err is not None and "requires" in err


def test_krpc_gear_sas_rcs_brake() -> None:
    driver = _driver()
    control = _Conn.space_center.active_vessel.control
    assert driver.execute("ksp.gear", {"deployed": True}) == (True, None)
    assert control.gear is True
    assert driver.execute("ksp.sas", {"enabled": True}) == (True, None)
    assert control.sas is True
    assert driver.execute("ksp.rcs", {"enabled": False}) == (True, None)
    assert control.rcs is False
    assert driver.execute("ksp.brake", {"enabled": True}) == (True, None)
    assert control.brakes is True


def test_krpc_reset_neutralizes_controls() -> None:
    driver = _driver()
    control = _Conn.space_center.active_vessel.control
    driver.execute("ksp.throttle", {"throttle": 1.0})
    driver.execute("ksp.steer", {"pitch": 0.8, "yaw": -0.5, "roll": 0.2})
    driver.reset()
    assert control.throttle == 0.0
    assert control.pitch == 0.0
    assert control.yaw == 0.0
    assert control.roll == 0.0


def test_krpc_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise OSError("refused")

    driver = KrpcDriver(host="127.0.0.1", rpc_port=1, stream_port=2, connect_fn=boom)
    ok, err = driver.execute("ksp.throttle", {})
    assert not ok
    assert err is not None and "refused" in err


class _AutoPilot:
    def __init__(self) -> None:
        self.pitch: float | None = None
        self.heading: float | None = None
        self.engaged = False
        self.ref: object = None

    def target_pitch_and_heading(self, pitch: float, heading: float) -> None:
        self.pitch = pitch
        self.heading = heading

    def engage(self) -> None:
        self.engaged = True

    def disengage(self) -> None:
        self.engaged = False

    @property
    def reference_frame(self) -> object:
        return self.ref

    @reference_frame.setter
    def reference_frame(self, value: object) -> None:
        self.ref = value


def test_krpc_fly_engages_surface_autopilot() -> None:
    vessel = _Conn.space_center.active_vessel
    autopilot = _AutoPilot()
    vessel.auto_pilot = autopilot  # type: ignore[attr-defined]
    vessel.surface_reference_frame = "srf"  # type: ignore[attr-defined]
    ok, err = _driver().execute(
        "ksp.fly",
        {"throttle": 1.0, "pitch_deg": 120, "heading_deg": 450, "stage": True},
    )
    assert ok and err is None
    assert vessel.control.throttle == 1.0
    assert vessel.control.staged == 1
    assert vessel.control.sas is False
    assert autopilot.engaged is True
    assert autopilot.pitch == 90.0
    assert autopilot.heading == 90.0
    assert autopilot.ref == "srf"
    assert autopilot.stopping_time == (2.0, 2.0, 2.0)
    assert autopilot.target_roll == 0.0

    ok, err = _driver().execute("ksp.fly", {"throttle": 0.0, "sas": True})
    assert ok and err is None
    assert autopilot.engaged is False
    assert vessel.control.sas is True
    assert vessel.control.throttle == 0.0

    vessel.control.throttle = 0.4
    _driver().reset()
    assert vessel.control.throttle == 0.0
    assert autopilot.engaged is False


def test_krpc_fly_damp_selects_stability_sas() -> None:
    class _SasMode:
        stability_assist = "stability"

    vessel = _Conn.space_center.active_vessel
    autopilot = _AutoPilot()
    autopilot.engaged = True
    vessel.auto_pilot = autopilot  # type: ignore[attr-defined]
    _Conn.space_center.SASMode = _SasMode  # type: ignore[attr-defined]
    ok, err = _driver().execute(
        "ksp.fly",
        {"throttle": 0.0, "sas": True, "sas_mode": "stability"},
    )
    assert ok and err is None
    assert autopilot.engaged is False
    assert vessel.control.sas is True
    assert vessel.control.sas_mode == "stability"  # type: ignore[attr-defined]
    assert vessel.control.throttle == 0.0
    assert vessel.control.staged == 0


def test_krpc_fly_without_autopilot_still_sets_throttle() -> None:
    ok, err = _driver().execute("ksp.fly", {"throttle": 0.55, "pitch_deg": 80, "heading_deg": 90})
    assert ok and err is None
    control = _Conn.space_center.active_vessel.control
    assert control.throttle == 0.55
    assert control.sas is True


def test_krpc_accepts_and_finishes_contracts_without_a_live_server() -> None:
    class _Param:
        def __init__(self, title: str, *, completed: bool = False) -> None:
            self.title = title
            self.notes = ""
            self.completed = completed
            self.failed = False
            self.optional = False
            self.children: list[object] = []

    class _Offer:
        def __init__(self) -> None:
            self.type = "AltitudeRecord"
            self.title = "Reach an altitude of 5,000m"
            self.state = "offered"
            self.seen = False
            self.accepted = False
            self.parameters = [_Param(self.title)]

        def accept(self) -> None:
            self.accepted = True
            self.state = "active"

    class _Done:
        def __init__(self) -> None:
            self.type = "AltitudeRecord"
            self.title = "Reach an altitude of 11,000m"
            self.state = "active"
            self.parameters = [_Param(self.title, completed=True)]
            self.completed_called = False

        def complete(self) -> None:
            self.completed_called = True
            self.state = "completed"

    class _RecoverContract:
        def __init__(self) -> None:
            self.type = "PartTest"
            self.title = "Test and recover"
            self.state = "active"
            self.parameters = [_Param("Recover the vessel")]

    class _Situation:
        name = "landed"

    class _RecoverVessel:
        def __init__(self) -> None:
            self.situation = _Situation()
            self.recovered = False

        def recover(self) -> None:
            self.recovered = True

    offer = _Offer()
    done = _Done()
    recover_contract = _RecoverContract()
    vessel = _RecoverVessel()

    class _Manager:
        @property
        def offered_contracts(self) -> list[object]:
            return [offer] if offer.state == "offered" else []

        @property
        def active_contracts(self) -> list[object]:
            return [item for item in (offer, done, recover_contract) if item.state == "active"]

        @property
        def completed_contracts(self) -> list[object]:
            return [done] if done.state == "completed" else []

    class _Center:
        contract_manager = _Manager()
        active_vessel = vessel

    class _Local:
        space_center = _Center()

    conn = _Local()
    driver = KrpcDriver(
        host="127.0.0.1",
        rpc_port=1,
        stream_port=2,
        connect_fn=lambda *_args: conn,
    )
    ok, err = driver.execute(
        "ksp.contract.accept",
        {"type": "AltitudeRecord", "title": "Reach an altitude of 5,000m"},
    )
    assert (ok, err) == (True, None)
    assert offer.accepted is True
    assert offer.seen is True

    ok, err = driver.execute(
        "ksp.contract.finish",
        {"type": "AltitudeRecord", "title": "Reach an altitude of 11,000m"},
    )
    assert (ok, err) == (True, None)
    assert done.completed_called is True

    ok, err = driver.execute("ksp.contract.finish", {"type": "PartTest", "title": "Test and recover"})
    assert (ok, err) == (True, None)
    assert vessel.recovered is True

    ok, err = driver.execute("ksp.contract.accept", {"type": "Nope", "title": "Missing"})
    assert ok is False
    assert err is not None and "not found" in err


def test_krpc_no_active_vessel() -> None:
    _Conn.space_center.active_vessel = None  # type: ignore[assignment]
    ok, err = _driver().execute("ksp.throttle", {"throttle": 0.5})
    assert not ok
    assert err is not None and "no active vessel" in err
