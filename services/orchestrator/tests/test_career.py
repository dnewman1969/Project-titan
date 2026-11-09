"""Career contract selection and the flight goal it produces. No live KSP."""

from __future__ import annotations

from titan_memory.learnings import FailedContract, exposed_failure_notes
from titan_orchestrator.career import (
    CareerMemory,
    advance_career,
    contract_key,
    failed_keys_from_rows,
)
from titan_orchestrator.flight_policy import decide_flight

_ALTITUDE = "Reach an altitude of 5,000m"
_PART = 'Test the LV-T30 "Reliant" Liquid Fuel Engine while landed at Kerbin'


def _param(
    title: str, *, completed: bool = False, failed: bool = False, notes: str = ""
) -> dict[str, object]:
    return {
        "title": title,
        "notes": notes,
        "completed": completed,
        "failed": failed,
        "optional": False,
    }


def _contract(
    title: str,
    parameters: list[dict[str, object]],
    *,
    contract_type: str = "Contract",
    state: str = "offered",
    funds_completion: float = 5000,
    science_completion: float = 2,
) -> dict[str, object]:
    return {
        "type": contract_type,
        "title": title,
        "state": state,
        "description": "",
        "synopsis": "",
        "notes": "",
        "funds_advance": 1000,
        "funds_completion": funds_completion,
        "funds_failure": 0,
        "reputation_completion": 1,
        "reputation_failure": 0,
        "science_completion": science_completion,
        "parameters": parameters,
    }


def _frame(
    *,
    mode: str = "career",
    available: bool = True,
    reason: str | None = None,
    offered: list[dict[str, object]] | None = None,
    active: list[dict[str, object]] | None = None,
    situation: str = "pre_launch",
    alt_m: float = 70,
    vertical: float = 0,
    apo: float | None = None,
    peri: float | None = None,
    parts: list[str] | None = None,
    liquid: float | None = 400,
    oxidizer: float | None = 480,
    solid: float | None = 0,
    scene: str = "flight",
) -> dict[str, object]:
    orbit = None
    if apo is not None:
        orbit = {
            "body": "Kerbin",
            "apoapsis_m": apo,
            "periapsis_m": peri if peri is not None else -500_000,
            "inclination_deg": 0,
            "eccentricity": 0.9,
        }
    return {
        "scene": scene,
        "paused": False,
        "environment": {"body": "Kerbin"},
        "vehicle": {
            "name": "Explorer",
            "situation": situation,
            "geo": {"lat_deg": 0.0, "lon_deg": 0.0, "alt_m": alt_m},
            "velocity": {"speed_mps": 40.0, "vertical_mps": vertical, "horizontal_mps": 10.0},
            "orbit": orbit,
        },
        "career": {
            "mode": mode,
            "available": available,
            "reason": reason,
            "funds": 12000,
            "science": 8,
            "reputation": 5,
            "offered": offered or [],
            "active": active or [],
            "failed": [],
            "vessel_parts": parts
            or ['LV-T30 "Reliant" Liquid Fuel Engine', "FL-T400 Fuel Tank", "Mk1 Command Pod"],
            "liquid_fuel": liquid,
            "oxidizer": oxidizer,
            "solid_fuel": solid,
        },
    }


def test_sandbox_is_named_and_does_not_invent_a_contract() -> None:
    memory = CareerMemory()
    frame = _frame(mode="sandbox", available=False, offered=[])
    directive = advance_career(memory, frame)
    assert directive.use_generic_fly is True
    assert directive.actions == ()
    assert directive.notes
    assert "not a career or science" in str(directive.notes[0].value["text"])
    again = advance_career(memory, frame)
    assert again.notes == ()


def test_lists_contracts_and_accepts_the_one_the_vessel_can_finish() -> None:
    memory = CareerMemory()
    offered = [
        _contract(
            "Fly by the Mun",
            [_param("Fly by the Mun")],
            contract_type="Flyby",
        ),
        _contract(
            "Put a satellite in orbit of Kerbin",
            [_param("Apoapsis: 250,000m"), _param("Periapsis: 250,000m"), _param("Inclination: 0")],
            contract_type="Satellite",
        ),
        _contract(_ALTITUDE, [_param(_ALTITUDE)], contract_type="AltitudeRecord"),
        _contract(
            "Test the Mainsail while flying",
            [_param('Test the RE-M3 "Mainsail" Liquid Fuel Engine while flying')],
            contract_type="PartTest",
        ),
    ]
    directive = advance_career(memory, _frame(offered=offered))
    assert directive.actions
    assert directive.actions[0].action_id == "ksp.contract.accept"
    assert directive.actions[0].params["title"] == _ALTITUDE
    why = directive.actions[0].rationale
    assert "Accepted" in why
    assert "Mun" in why
    assert (
        "satellite" in why.lower()
        or "orbit shape" in why.lower()
        or "Apoapsis" in why
        or "inclination" in why
    )
    assert any(note.section == "discoveries" and note.key == "career.board" for note in directive.notes)
    board = next(note.value["text"] for note in directive.notes if note.key == "career.board")
    assert "Offered:" in board
    assert _ALTITUDE in board
    assert "5,000 funds" in board or "5000" in board
    assert any(note.section == "lessons" and note.value.get("ok") is True for note in directive.notes)
    assert any(note.section == "goals" for note in directive.notes)
    assert directive.goal is not None and directive.goal.kind == "hold"


def test_landed_part_test_beats_a_climb_when_the_part_is_installed() -> None:
    memory = CareerMemory()
    offered = [
        _contract(_ALTITUDE, [_param(_ALTITUDE)], contract_type="AltitudeRecord"),
        _contract(_PART, [_param(_PART)], contract_type="PartTest"),
    ]
    directive = advance_career(memory, _frame(offered=offered))
    assert directive.actions[0].params["title"] == _PART
    assert "LV-T30" in directive.actions[0].rationale
    active = [_contract(_PART, [_param(_PART)], contract_type="PartTest", state="active")]
    flying = advance_career(CareerMemory(), _frame(active=active))
    assert flying.goal is not None and flying.goal.kind == "part_test"
    decision = decide_flight(_frame(active=active), goal=flying.goal)
    assert decision.stage_once is False
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 0.0
    assert decision.proposal["params"].get("sas") is True


def test_altitude_goal_stops_at_the_contract_instead_of_coasting_to_orbit() -> None:
    memory = CareerMemory()
    active = [
        _contract(
            _ALTITUDE,
            [_param(_ALTITUDE)],
            contract_type="AltitudeRecord",
            state="active",
        )
    ]
    low = advance_career(
        memory,
        _frame(active=active, situation="flying", alt_m=1000, vertical=80),
    )
    assert low.goal is not None and low.goal.kind == "altitude"
    decision = decide_flight(
        _frame(active=active, situation="flying", alt_m=1000, vertical=80),
        goal=low.goal,
    )
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 1.0
    assert decision.proposal["params"]["heading_deg"] == 90.0
    assert "5,000" in decision.message or "5000" in decision.message
    assert decision.status == "contract_ascent"
    assert "80 km" not in decision.message

    met = decide_flight(
        _frame(active=active, situation="flying", alt_m=6000, vertical=10),
        goal=low.goal,
    )
    assert met.proposal is not None
    assert met.proposal["params"]["throttle"] == 0.0
    assert met.proposal["params"]["sas"] is True
    assert "pitch_deg" not in met.proposal["params"]


def test_orbit_goal_circularizes_near_apoapsis() -> None:
    memory = CareerMemory()
    title = "Achieve a stable orbit around Kerbin"
    active = [_contract(title, [_param(title)], contract_type="Orbit", state="active")]
    directive = advance_career(
        memory,
        _frame(
            active=active,
            situation="flying",
            alt_m=72_000,
            vertical=4,
            apo=85_000,
            peri=-20_000,
        ),
    )
    assert directive.goal is not None and directive.goal.kind == "orbit"
    decision = decide_flight(
        _frame(
            active=active,
            situation="flying",
            alt_m=72_000,
            vertical=4,
            apo=85_000,
            peri=-20_000,
        ),
        goal=directive.goal,
    )
    assert decision.status == "contract_circularize"
    assert decision.proposal is not None
    assert decision.proposal["params"]["throttle"] == 1.0
    assert decision.proposal["params"]["pitch_deg"] == 5.0


def test_completed_parameters_request_turn_in() -> None:
    memory = CareerMemory()
    active = [
        _contract(
            _ALTITUDE,
            [_param(_ALTITUDE, completed=True)],
            contract_type="AltitudeRecord",
            state="active",
        )
    ]
    directive = advance_career(memory, _frame(active=active, situation="flying", alt_m=6000, vertical=0))
    assert directive.actions
    assert directive.actions[0].action_id == "ksp.contract.finish"
    assert any(note.section == "lessons" and note.value.get("ok") is True for note in directive.notes)


def test_part_test_then_recover_advances_the_step() -> None:
    memory = CareerMemory()
    title = "Test the Reliant in flight"
    test = 'Test the LV-T30 "Reliant" Liquid Fuel Engine while flying'
    active = [
        _contract(
            title,
            [_param(test), _param("Recover the vessel")],
            contract_type="PartTest",
            state="active",
        )
    ]
    flying = advance_career(memory, _frame(active=active, situation="flying", alt_m=1500, vertical=20))
    assert flying.goal is not None and flying.goal.kind == "part_test"
    assert flying.actions == ()
    done_test = [
        _contract(
            title,
            [_param(test, completed=True), _param("Recover the vessel")],
            contract_type="PartTest",
            state="active",
        )
    ]
    recover = advance_career(
        memory,
        _frame(active=done_test, situation="landed", alt_m=70, vertical=0),
    )
    assert recover.goal is not None and recover.goal.kind == "recover"
    assert recover.actions
    assert recover.actions[0].action_id == "ksp.contract.finish"


def test_failure_is_a_lesson_and_blocks_the_same_contract() -> None:
    memory = CareerMemory()
    active = [
        _contract(
            _ALTITUDE,
            [_param(_ALTITUDE)],
            contract_type="AltitudeRecord",
            state="active",
        )
    ]
    failed = advance_career(
        memory,
        _frame(
            active=active,
            situation="flying",
            alt_m=2200,
            vertical=-30,
            liquid=0,
            oxidizer=0,
            solid=0,
        ),
    )
    lessons = [note for note in failed.notes if note.section == "lessons"]
    assert lessons
    assert lessons[0].value["ok"] is False
    text = str(lessons[0].value["text"])
    assert "Do not accept contract key" in text
    assert "out of fuel" in text
    key = contract_key("AltitudeRecord", _ALTITUDE)
    assert key in memory.failed_keys

    offered = advance_career(
        memory,
        _frame(
            offered=[
                _contract(_ALTITUDE, [_param(_ALTITUDE)], contract_type="AltitudeRecord"),
            ],
            situation="pre_launch",
            liquid=400,
            oxidizer=480,
        ),
    )
    assert offered.actions == ()
    idle = next(note.value["text"] for note in offered.notes if note.key == "career.idle")
    assert "already failed" in idle
    assert "Not accepting" in idle


def test_prior_lesson_text_is_enough_to_refuse_the_contract() -> None:
    key = contract_key("AltitudeRecord", _ALTITUDE)
    found = failed_keys_from_rows(
        [
            {
                "section": "notes",
                "key": "prior.00",
                "value": {
                    "text": f"Do not accept contract key `{key}` ({_ALTITUDE}) again: out of fuel.",
                    "prior_memory": True,
                },
            }
        ]
    )
    assert found == {key}
    memory = CareerMemory(failed_keys=found, loaded_failures=True)
    directive = advance_career(
        memory,
        _frame(offered=[_contract(_ALTITUDE, [_param(_ALTITUDE)], contract_type="AltitudeRecord")]),
    )
    assert directive.actions == ()


def test_stored_failure_loads_as_the_skip_list() -> None:
    """The durable note is the row the career loop already refuses. Fly policy is untouched."""
    key = contract_key("AltitudeRecord", _ALTITUDE)
    notes = exposed_failure_notes(
        [
            FailedContract(
                contract_id=key,
                title=_ALTITUDE,
                reason="out of fuel at 2200 m",
                session_id="00000000-0000-4000-8000-00000000c0de",
                game_slug="ksp",
            )
        ]
    )
    found = failed_keys_from_rows(
        [{"section": "notes", "key": note_key, "value": value} for note_key, value in notes]
    )
    assert found == {key}
    memory = CareerMemory(failed_keys=found, loaded_failures=True)
    directive = advance_career(
        memory,
        _frame(offered=[_contract(_ALTITUDE, [_param(_ALTITUDE)], contract_type="AltitudeRecord")]),
    )
    assert directive.actions == ()
    idle = next(note.value["text"] for note in directive.notes if note.key == "career.idle")
    assert "already failed" in idle


def test_missing_career_field_keeps_the_generic_ascent() -> None:
    decision = decide_flight(
        {
            "scene": "flight",
            "paused": False,
            "vehicle": {
                "name": "Explorer",
                "situation": "flying",
                "geo": {"alt_m": 22625.0},
                "velocity": {"vertical_mps": 40.0},
            },
        }
    )
    assert decision.proposal is not None
    assert decision.proposal["params"]["heading_deg"] == 90.0
    assert decision.proposal["params"]["pitch_deg"] == 45.0
    assert decision.status == "heading"
