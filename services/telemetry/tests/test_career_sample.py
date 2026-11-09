"""Fake kRPC contract manager. No live KSP."""

from __future__ import annotations

from titan_game_ksp.adapter import KspAdapter
from titan_game_ksp.career_sample import sample_career
from titan_game_ksp.vessel_sample import sample_vessel


class _Enum:
    def __init__(self, name: str) -> None:
        self.name = name


class _Param:
    def __init__(self, title: str, *, children: list[_Param] | None = None) -> None:
        self.title = title
        self.notes = "Reach it on Kerbin."
        self.completed = False
        self.failed = False
        self.optional = False
        self.children = children or []


class _Contract:
    def __init__(self, title: str, state: str, parameters: list[_Param]) -> None:
        self.type = "AltitudeRecord"
        self.title = title
        self.state = _Enum(state)
        self.description = "Climb."
        self.synopsis = "Up."
        self.notes = ""
        self.funds_advance = 2000.0
        self.funds_completion = 8000.0
        self.funds_failure = 0.0
        self.reputation_completion = 3.0
        self.reputation_failure = -1.0
        self.science_completion = 4.0
        self.parameters = parameters


class _Resource:
    def __init__(self, name: str, amount: float) -> None:
        self.name = name
        self.amount = amount


class _Resources:
    def __init__(self) -> None:
        self.all = [_Resource("LiquidFuel", 180.0), _Resource("Oxidizer", 220.0), _Resource("SolidFuel", 0.0)]

    def amount(self, name: str) -> float:
        for resource in self.all:
            if resource.name == name:
                return resource.amount
        return 0.0


class _Part:
    def __init__(self, title: str) -> None:
        self.title = title
        self.name = title


class _Parts:
    def __init__(self) -> None:
        self.all = [_Part('LV-T30 "Reliant" Liquid Fuel Engine'), _Part("FL-T400 Fuel Tank")]


class _Vessel:
    def __init__(self) -> None:
        self.name = "Explorer"
        self.parts = _Parts()
        self.resources = _Resources()


class _Manager:
    def __init__(self, offered: list[_Contract], active: list[_Contract]) -> None:
        self.offered_contracts = offered
        self.active_contracts = active
        self.failed_contracts = []


class _Center:
    def __init__(self, mode: str, manager: object | None) -> None:
        self.game_mode = _Enum(mode)
        self.funds = 25000.0
        self.science = 12.5
        self.reputation = 7.0
        self.contract_manager = manager
        self.active_vessel = _Vessel()


class _Conn:
    def __init__(self, center: _Center) -> None:
        self.space_center = center


def test_sample_lists_offered_and_active_parameters() -> None:
    parent = _Param("Complete the climb", children=[_Param("Reach an altitude of 5,000m")])
    offered = [_Contract("Reach an altitude of 5,000m", "offered", [parent])]
    active = [_Contract("Test the Reliant", "active", [_Param("Test the Reliant while flying")])]
    snapshot = sample_career(_Conn(_Center("career", _Manager(offered, active))))
    assert snapshot["mode"] == "career"
    assert snapshot["available"] is True
    assert snapshot["funds"] == 25000.0
    assert snapshot["offered"][0]["title"] == "Reach an altitude of 5,000m"
    assert snapshot["offered"][0]["parameters"][0]["title"] == "Reach an altitude of 5,000m"
    assert snapshot["offered"][0]["funds_completion"] == 8000.0
    assert snapshot["active"][0]["state"] == "active"
    assert snapshot["active"][0]["parameters"][0]["title"] == "Test the Reliant while flying"
    assert 'LV-T30 "Reliant" Liquid Fuel Engine' in snapshot["vessel_parts"]
    assert snapshot["liquid_fuel"] == 180.0
    assert snapshot["oxidizer"] == 220.0


def test_sandbox_does_not_pretend_contracts_exist() -> None:
    snapshot = sample_career(_Conn(_Center("sandbox", None)))
    assert snapshot["mode"] == "sandbox"
    assert snapshot["available"] is False
    assert snapshot["offered"] == []
    assert "does not" in snapshot["reason"]


def test_science_without_a_manager_says_so() -> None:
    snapshot = sample_career(_Conn(_Center("science", None)))
    assert snapshot["available"] is False
    assert "ContractManager" in snapshot["reason"]


def test_vessel_sample_and_adapter_carry_the_snapshot() -> None:
    class _Scene:
        name = "flight"

    class _Krpc:
        current_game_scene = _Scene()
        paused = False

    class _Flight:
        mean_altitude = 100.0
        latitude = 0.0
        longitude = 0.0
        speed = 0.0
        vertical_speed = 0.0
        horizontal_speed = 0.0
        heading = 90.0
        pitch = 90.0
        roll = 0.0

    class _Situation:
        name = "pre_launch"

    class _VesselFlight(_Vessel):
        situation = _Situation()
        surface_reference_frame = None
        control = type("C", (), {"throttle": 0.0, "sas": True, "rcs": False, "current_stage": 0})()
        orbit = None

        def flight(self, _ref: object = None) -> _Flight:
            return _Flight()

    center = _Center("career", _Manager([_Contract("Reach an altitude of 5,000m", "offered", [])], []))
    center.active_vessel = _VesselFlight()

    class _Both:
        space_center = center
        krpc = _Krpc()

    raw = sample_vessel(_Both())
    assert raw["career"]["available"] is True
    assert raw["liquid_fuel"] == 180.0
    frame = KspAdapter().normalize(raw)
    assert frame.career is not None
    assert frame.career.mode == "career"
    assert frame.career.offered[0].title == "Reach an altitude of 5,000m"
    assert frame.economy is not None
    assert frame.economy.funds == 25000.0
    assert frame.vehicle.name == "Explorer"
