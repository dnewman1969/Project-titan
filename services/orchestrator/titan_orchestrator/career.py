"""KSP career: read contracts, fly one the vessel can finish, then the next.

A human in career opens Mission Control, reads offered contracts (altitude,
orbit, part test, recover, and the ones that are obviously out of reach),
accepts one the current rocket can do, then flies each parameter in order.
When that contract has been turned in, the funds, science, and reputation on
the telemetry snapshot — the kRPC SpaceCenter reading — are written on the
blackboard, and the next offered contract this vessel can finish is accepted.
Its parameters become the fly goal through the same path. A miss, or no
acceptable contract, stops the chain. Failed ids and ones already turned in
are not accepted again.

Stock kRPC exposes that same ContractManager. This module is the decision
half: it does not open a socket. Telemetry carries the snapshot; actions
call ``accept`` and, when the API allows it, finish or recover.

Lessons use the blackboard ``lessons`` shape the session-end memory path
already stores (``text``, and ``ok`` false for a miss). The contract key is
in the text so a later session that only has the prior-memory line still
refuses the same contract.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

_BODIES = (
    "moho",
    "eve",
    "gilly",
    "kerbin",
    "mun",
    "minmus",
    "duna",
    "ike",
    "dres",
    "jool",
    "laythe",
    "vall",
    "tylo",
    "bop",
    "pol",
    "eeloo",
)
_MODES = frozenset({"career", "science"})
_UNPLANNABLE = re.compile(
    r"\b(apoapsis|periapsis|inclination|eccentricity|rendezvous|dock(?:ing)?|station|asteroid|satellite)\b",
    re.IGNORECASE,
)
_METERS = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(km|m|meters?)\b",
    re.IGNORECASE,
)
_PART = re.compile(
    r"test(?:\s+the)?\s+(.+?)"
    r"(?:\s+while\b|\s+in flight\b|\s+in orbit\b|\s+on a\b|\s+at an\b|\s+at the\b|\s+over\b|$)",
    re.IGNORECASE,
)
_KEY_IN_TEXT = re.compile(r"contract key `([^`]+)`", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+")
_PART_STOP = frozenset(
    {
        "the",
        "while",
        "test",
        "liquid",
        "fuel",
        "engine",
        "solid",
        "booster",
        "rocket",
        "over",
        "kerbin",
        "and",
        "for",
        "with",
        "from",
    }
)
_ORBIT_FUEL = (200.0, 220.0)
_ACCEPT_WAIT_LIMIT = 5


@dataclass(frozen=True)
class ContractParam:
    title: str
    notes: str
    completed: bool
    failed: bool
    optional: bool


@dataclass(frozen=True)
class ContractView:
    type: str
    title: str
    state: str
    description: str
    synopsis: str
    notes: str
    funds_advance: float | None
    funds_completion: float | None
    funds_failure: float | None
    reputation_completion: float | None
    reputation_failure: float | None
    science_completion: float | None
    parameters: tuple[ContractParam, ...]

    @property
    def key(self) -> str:
        return contract_key(self.type, self.title)


@dataclass(frozen=True)
class CareerView:
    mode: str | None
    available: bool
    reason: str | None
    funds: float | None
    science: float | None
    reputation: float | None
    offered: tuple[ContractView, ...]
    active: tuple[ContractView, ...]
    failed: tuple[ContractView, ...]
    parts: tuple[str, ...]
    liquid_fuel: float | None
    oxidizer: float | None
    solid_fuel: float | None


@dataclass(frozen=True)
class FlightGoal:
    """One parameter the fly policy should pursue instead of a generic climb."""

    kind: str
    contract_key: str
    contract_title: str
    parameter_title: str
    summary: str
    altitude_m: float | None = None
    altitude_min_m: float | None = None
    altitude_max_m: float | None = None
    situation: str | None = None
    part: str | None = None


@dataclass(frozen=True)
class ContractPlan:
    key: str
    type: str
    title: str
    steps: tuple[FlightGoal, ...]


@dataclass(frozen=True)
class CareerAction:
    action_id: str
    params: dict[str, Any]
    rationale: str
    expected_effect: str


@dataclass(frozen=True)
class BoardNote:
    section: Literal["discoveries", "lessons", "goals", "notes"]
    key: str
    value: dict[str, Any]
    author_kind: Literal["agent", "director"]
    author_id: str


@dataclass(frozen=True)
class CareerDirective:
    """What the flight loop should do with one telemetry frame."""

    use_generic_fly: bool
    goal: FlightGoal | None = None
    actions: tuple[CareerAction, ...] = ()
    notes: tuple[BoardNote, ...] = ()


@dataclass
class CareerMemory:
    """Session memory so a failed contract is not accepted again."""

    failed_keys: set[str] = field(default_factory=set)
    loaded_failures: bool = False
    mode_text: str | None = None
    board_text: str | None = None
    idle_text: str | None = None
    goal_text: str | None = None
    accepted_key: str | None = None
    accept_waits: int = 0
    completed_keys: set[str] = field(default_factory=set)
    noted_failures: set[str] = field(default_factory=set)
    unparsed: set[str] = field(default_factory=set)
    goal_key: str = ""
    peak_alt: float = 0.0
    saw_airborne: bool = False
    finish_for: str = ""
    finish_ticks: int = 0
    completed_titles: dict[str, str] = field(default_factory=dict)
    payout_noted: set[str] = field(default_factory=set)
    chain_stopped: bool = False


def contract_key(contract_type: str, title: str) -> str:
    return f"{_norm(contract_type)}|{_norm(title)}"


def career_from_frame(frame: Mapping[str, Any]) -> CareerView | None:
    raw = frame.get("career")
    if not isinstance(raw, dict):
        return None
    return CareerView(
        mode=_norm(raw.get("mode")) or None,
        available=bool(raw.get("available")),
        reason=_text(raw.get("reason")),
        funds=_float(raw.get("funds")),
        science=_float(raw.get("science")),
        reputation=_float(raw.get("reputation")),
        offered=_contracts(raw.get("offered")),
        active=_contracts(raw.get("active")),
        failed=_contracts(raw.get("failed")),
        parts=_parts(raw.get("vessel_parts")),
        liquid_fuel=_float(raw.get("liquid_fuel")),
        oxidizer=_float(raw.get("oxidizer")),
        solid_fuel=_float(raw.get("solid_fuel")),
    )


def unsupported_reason(view: CareerView) -> str | None:
    """None when this save can run the career loop. Otherwise the blackboard line."""
    if view.mode not in _MODES:
        shown = view.mode or "unknown"
        return (
            f"This save is {shown}, not a career or science game. "
            "Contracts are not available, so none will be accepted or invented."
        )
    if not view.available:
        detail = view.reason or "ContractManager returned nothing."
        return (
            f"Game mode is {view.mode}, but contracts cannot be read ({detail}). "
            "Not treating the flight as a contract."
        )
    return None


def failed_keys_from_rows(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    """Keys already stored as lessons or prior-memory notes."""
    found: set[str] = set()
    for row in rows:
        value = row.get("value")
        if not isinstance(value, dict):
            continue
        raw_text = value.get("text")
        text = raw_text if isinstance(raw_text, str) else ""
        refused = value.get("ok") is False or "do not accept contract key" in text.lower()
        if not refused:
            continue
        key = value.get("contract_key")
        if isinstance(key, str) and key.strip():
            found.add(key.strip())
        match = _KEY_IN_TEXT.search(text)
        if match:
            found.add(match.group(1).strip())
    return found


def advance_career(memory: CareerMemory, frame: Mapping[str, Any]) -> CareerDirective:
    """One career tick. Mutates ``memory`` and returns fly/accept/finish work."""
    view = career_from_frame(frame)
    if view is None:
        return CareerDirective(use_generic_fly=True)
    blocked = unsupported_reason(view)
    if blocked is not None:
        notes: list[BoardNote] = []
        if memory.mode_text != blocked:
            memory.mode_text = blocked
            notes.append(
                _note(
                    "discoveries",
                    "career.mode",
                    {"text": blocked, "action_id": None},
                    "agent",
                    "flight_engineer",
                )
            )
        return CareerDirective(use_generic_fly=True, notes=tuple(notes))

    notes = []
    board = format_board(view)
    if memory.board_text != board:
        memory.board_text = board
        notes.append(
            _note(
                "discoveries",
                "career.board",
                {"text": board, "action_id": None},
                "agent",
                "flight_engineer",
            )
        )
    body = frame_body(frame)
    for failed in view.failed:
        memory.failed_keys.add(failed.key)
    _mark_game_failures(memory, notes, view)
    if not memory.chain_stopped:
        plan, contract = _select_active(view, memory, body, notes)
        if plan is not None and contract is not None:
            _track(memory, plan.key, frame)
            failure = _flight_failure(frame, contract, plan, memory)
            if failure is not None:
                _remember_failure(memory, notes, contract, failure)
                _reset_track(memory)
                return CareerDirective(
                    use_generic_fly=False,
                    goal=_hold(
                        f"Stopping after a miss on {contract.title}. Not accepting another contract.",
                        key=contract.key,
                        title=contract.title,
                    ),
                    notes=tuple(notes),
                )
            return _fly_plan(memory, notes, frame, plan, contract)
        pending = _awaiting_turn_in(view, memory)
        if pending is not None:
            return _turn_in_hold(memory, notes, pending)

    # One payout per turned-in contract. The next tick cannot accept it again.
    _record_payouts(memory, notes, view)
    if memory.chain_stopped:
        return _idle_directive(memory, notes, view, body, stopped=True)

    waiting = _waiting_on_accept(memory, view, notes)
    if waiting == "miss":
        return _idle_directive(memory, notes, view, body, stopped=True)
    if waiting == "wait":
        title = _title_for(view, memory.accepted_key) or "the contract"
        summary = f"Waiting for {title} to become active before launching."
        return CareerDirective(
            use_generic_fly=False,
            goal=_hold(summary, key=memory.accepted_key or ""),
            notes=tuple(notes),
        )

    choice = _choose(view, failed=memory.failed_keys, completed=memory.completed_keys, body=body)
    if choice is None:
        return _idle_directive(memory, notes, view, body, stopped=False)

    memory.accepted_key = choice.plan.key
    memory.accept_waits = 0
    memory.idle_text = None
    why = choice.why
    notes.append(
        _note(
            "lessons",
            f"career.accept.{_slug(choice.plan.key)}",
            {
                "text": why,
                "ok": True,
                "contract_key": choice.plan.key,
                "contract_title": choice.plan.title,
                "contract_type": choice.plan.type,
                "action_id": "ksp.contract.accept",
            },
            "agent",
            "director",
        )
    )
    goal_line = f"Accepted {choice.plan.title}: {choice.step_line}"
    if memory.goal_text != goal_line:
        memory.goal_text = goal_line
        notes.append(_goal_note(goal_line, choice.plan.key))
    return CareerDirective(
        use_generic_fly=False,
        goal=_hold(f"Accepted {choice.plan.title}. Not launching until it is active."),
        actions=(
            CareerAction(
                action_id="ksp.contract.accept",
                params={"type": choice.plan.type, "title": choice.plan.title},
                rationale=why,
                expected_effect="The offered contract becomes active.",
            ),
        ),
        notes=tuple(notes),
    )


def _idle_directive(
    memory: CareerMemory,
    notes: list[BoardNote],
    view: CareerView,
    body: str,
    *,
    stopped: bool,
) -> CareerDirective:
    if stopped:
        idle = _standdown_line(view, memory, body)
    else:
        idle = _idle_line(view, memory.failed_keys, memory.completed_keys, body)
    if memory.idle_text != idle:
        memory.idle_text = idle
        notes.append(
            _note(
                "discoveries",
                "career.idle",
                {"text": idle, "action_id": None},
                "agent",
                "flight_engineer",
            )
        )
    return CareerDirective(use_generic_fly=False, goal=_hold(idle), notes=tuple(notes))


def _standdown_line(view: CareerView, memory: CareerMemory, body: str) -> str:
    """Miss ends the chain even when another offered contract is flyable."""
    choice = _choose(view, failed=memory.failed_keys, completed=memory.completed_keys, body=body)
    if choice is None:
        return _idle_line(view, memory.failed_keys, memory.completed_keys, body)
    return f"Stopped after a miss. Not accepting {choice.plan.title!r} or any other contract."


def _awaiting_turn_in(view: CareerView, memory: CareerMemory) -> ContractView | None:
    """The contract whose parameters are done and that is still active."""
    for contract in view.active:
        if contract.key not in memory.completed_keys or contract.key in memory.failed_keys:
            continue
        if contract.state == "completed":
            continue
        return contract
    return None


def _turn_in_hold(memory: CareerMemory, notes: list[BoardNote], contract: ContractView) -> CareerDirective:
    memory.completed_titles.setdefault(contract.key, contract.title)
    goal_line = f"Complete {contract.title}"
    if memory.goal_text != goal_line:
        memory.goal_text = goal_line
        notes.append(_goal_note(goal_line, contract.key))
    return CareerDirective(
        use_generic_fly=False,
        goal=_hold(
            f"{contract.title} is complete. Holding for turn-in.",
            key=contract.key,
            title=contract.title,
        ),
        actions=_finish_actions(memory, contract, "Parameters are complete."),
        notes=tuple(notes),
    )


def _record_payouts(memory: CareerMemory, notes: list[BoardNote], view: CareerView) -> None:
    """Write funds, science, and reputation once the contract has left the active list.

    The snapshot is the kRPC ``SpaceCenter`` reading (``funds``, ``science``,
    ``reputation``). One note per contract, so a later tick does not write it again.
    """
    for key in sorted(memory.completed_keys):
        if key in memory.payout_noted or key in memory.failed_keys:
            continue
        if _still_active(view, key):
            continue
        memory.payout_noted.add(key)
        title = memory.completed_titles.get(key) or _title_for(view, key) or key
        notes.append(
            _note(
                "discoveries",
                f"career.payout.{_slug(key)}",
                {
                    "text": (
                        f"Turned in {title!r}. "
                        f"Funds {_num_text(view.funds)}, science {_num_text(view.science)}, "
                        f"reputation {_num_text(view.reputation)}."
                    ),
                    "funds": view.funds,
                    "science": view.science,
                    "reputation": view.reputation,
                    "contract_key": key,
                    "contract_title": title,
                    "action_id": None,
                },
                "agent",
                "flight_engineer",
            )
        )


def _still_active(view: CareerView, key: str) -> bool:
    return any(contract.key == key and contract.state != "completed" for contract in view.active)


def _num_text(value: float | None) -> str:
    if value is None:
        return "unknown"
    rendered = f"{value:.2f}".rstrip("0").rstrip(".")
    return rendered or "0"


def format_board(view: CareerView) -> str:
    economy = _economy_phrase(view)
    offered = _contract_phrases(view.offered) or "none"
    active = _contract_phrases(view.active) or "none"
    text = f"{economy}Offered: {offered}. Active: {active}."
    return text if len(text) <= 1400 else text[:1397] + "..."


def frame_body(frame: Mapping[str, Any]) -> str:
    env = frame.get("environment")
    if isinstance(env, dict):
        body = env.get("body")
        if isinstance(body, str) and body.strip():
            return body.strip()
    vehicle = frame.get("vehicle")
    if isinstance(vehicle, dict):
        orbit = vehicle.get("orbit")
        if isinstance(orbit, dict):
            body = orbit.get("body")
            if isinstance(body, str) and body.strip():
                return body.strip()
    return "Kerbin"


def reachable_altitude_m(view: CareerView) -> float:
    """Metres this vessel can plausibly be asked to reach. Unknown fuel is conservative."""
    known = view.liquid_fuel is not None or view.oxidizer is not None or view.solid_fuel is not None
    liquid = view.liquid_fuel or 0.0
    oxidizer = view.oxidizer or 0.0
    solid = view.solid_fuel or 0.0
    if known:
        if liquid >= _ORBIT_FUEL[0] and oxidizer >= _ORBIT_FUEL[1]:
            return 250_000.0
        if liquid >= 40 and oxidizer >= 40:
            return 100_000.0
        if solid >= 100 or liquid >= 10:
            return 30_000.0
        if solid > 0 or liquid > 0 or oxidizer > 0:
            return 8_000.0
        return 500.0
    names = " ".join(view.parts).lower()
    if "liquid" in names and "engine" in names:
        return 40_000.0
    if "booster" in names or "solid" in names:
        return 15_000.0
    return 0.0


def can_attempt_orbit(view: CareerView) -> bool:
    if view.liquid_fuel is not None or view.oxidizer is not None:
        return (view.liquid_fuel or 0.0) >= _ORBIT_FUEL[0] and (view.oxidizer or 0.0) >= _ORBIT_FUEL[1]
    names = " ".join(view.parts).lower()
    return "liquid" in names and "engine" in names and ("tank" in names or "fl-t" in names)


def part_installed(phrase: str, parts: Sequence[str]) -> bool:
    if not phrase.strip() or not parts:
        return False
    needle = phrase.lower()
    for part in parts:
        hay = part.lower()
        if hay and (hay in needle or needle in hay):
            return True
    tokens = [token for token in _TOKEN.findall(needle) if len(token) > 2 and token not in _PART_STOP]
    if not tokens:
        return False
    for part in parts:
        hay = part.lower()
        if all(token in hay for token in tokens[:4]):
            return True
        for token in tokens:
            if any(ch.isdigit() for ch in token) and token in hay:
                return True
    return False


@dataclass(frozen=True)
class _Choice:
    plan: ContractPlan
    why: str
    step_line: str


def _choose(
    view: CareerView,
    *,
    failed: set[str],
    completed: set[str],
    body: str,
) -> _Choice | None:
    ranked: list[tuple[float, ContractPlan, ContractView]] = []
    skipped: list[tuple[ContractView, str]] = []
    for contract in view.offered:
        if contract.key in failed:
            skipped.append((contract, "it already failed and will not be accepted again"))
            continue
        if contract.key in completed:
            skipped.append((contract, "it is already complete"))
            continue
        plan, reason = _assess(contract, view, body=body, committed=False)
        if plan is None:
            skipped.append((contract, reason))
            continue
        ranked.append((_score(plan), plan, contract))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1].title))
    _score_value, plan, contract = ranked[0]
    for _score_value, _other, other_contract in ranked[1:]:
        skipped.append((other_contract, "a contract this vessel can finish more easily is available"))
    return _Choice(plan=plan, why=_why(plan, contract, view, skipped), step_line=_step_line(plan))


def _assess(
    contract: ContractView,
    view: CareerView,
    *,
    body: str,
    committed: bool,
) -> tuple[ContractPlan | None, str]:
    foreign = _foreign(contract.title, body)
    if foreign is not None:
        return None, f"it targets {foreign.title()}"
    required = [param for param in contract.parameters if not param.optional]
    if not required:
        return None, "it has no required parameters"
    steps: list[FlightGoal] = []
    for param in required:
        parsed = _parse_param(param, contract, body)
        if isinstance(parsed, str):
            return None, parsed
        if not committed:
            unfit = _fits(parsed, view)
            if unfit is not None:
                return None, unfit
        steps.append(parsed)
    return (
        ContractPlan(key=contract.key, type=contract.type, title=contract.title, steps=tuple(steps)),
        "",
    )


def _parse_param(param: ContractParam, contract: ContractView, body: str) -> FlightGoal | str:
    text = f"{param.title} {param.notes}".strip()
    foreign = _foreign(text, body) or _foreign(contract.title, body)
    if foreign is not None:
        return f"parameter {param.title!r} mentions {foreign.title()}"
    if _UNPLANNABLE.search(text):
        return f"parameter {param.title!r} needs an orbit shape or rendezvous this loop cannot fly"
    if re.search(r"\brecover\b", text, re.IGNORECASE):
        return _goal(contract, param, kind="recover", summary="land and recover the vessel")
    if re.search(r"\btest\b", text, re.IGNORECASE):
        return _part_goal(contract, param, text)
    if re.search(r"sub-?orbital", text, re.IGNORECASE):
        return _goal(
            contract,
            param,
            kind="suborbital",
            summary="fly a sub-orbital arc above the atmosphere",
            altitude_m=70_000.0,
        )
    if re.search(r"stable orbit|\borbit\b", text, re.IGNORECASE):
        return _goal(
            contract,
            param,
            kind="orbit",
            summary="reach orbit and circularize above the atmosphere",
        )
    if re.search(r"\baltitude\b", text, re.IGNORECASE) or _METERS.search(text):
        return _altitude_goal(contract, param, text)
    return f"parameter {param.title!r} is not an altitude, orbit, part test, or recovery"


def _part_goal(contract: ContractView, param: ContractParam, text: str) -> FlightGoal | str:
    match = _PART.search(text)
    part = match.group(1).strip(" .") if match else ""
    if not part:
        return f"parameter {param.title!r} does not name the part to test"
    situation = _situation_phrase(text) or "flying"
    numbers = _meters(text)
    lo: float | None = None
    hi: float | None = None
    if "between" in text.lower() and len(numbers) >= 2:
        lo, hi = sorted(numbers[:2])
    summary = f"test {part} ({situation.replace('_', ' ')})"
    if lo is not None and hi is not None:
        summary = f"test {part} between {lo:.0f} m and {hi:.0f} m"
    return _goal(
        contract,
        param,
        kind="part_test",
        summary=summary,
        situation=situation,
        part=part,
        altitude_min_m=lo,
        altitude_max_m=hi,
    )


def _altitude_goal(contract: ContractView, param: ContractParam, text: str) -> FlightGoal | str:
    numbers = _meters(text)
    if "between" in text.lower() and len(numbers) >= 2:
        lo, hi = sorted(numbers[:2])
        return _goal(
            contract,
            param,
            kind="altitude",
            summary=f"climb into {lo:.0f}-{hi:.0f} m",
            altitude_m=hi,
            altitude_min_m=lo,
            altitude_max_m=hi,
        )
    if not numbers:
        return f"parameter {param.title!r} does not give an altitude in metres"
    target = numbers[0]
    return _goal(
        contract,
        param,
        kind="altitude",
        summary=f"reach {target:.0f} m",
        altitude_m=target,
    )


def _fits(goal: FlightGoal, view: CareerView) -> str | None:
    if goal.part and not part_installed(goal.part, view.parts):
        if not view.parts:
            return "the vessel's parts were not read, so a part test cannot be confirmed"
        return f"the vessel does not carry {goal.part}"
    need = _metres_needed(goal)
    if need is not None and need > reachable_altitude_m(view) + 500:
        return f"the target is about {need:.0f} m and this vessel's fuel looks short of that"
    orbital = goal.kind == "orbit" or (goal.kind == "part_test" and goal.situation == "orbiting")
    if orbital and not can_attempt_orbit(view):
        return "an orbit needs more liquid fuel and oxidizer than this vessel shows"
    return None


def _metres_needed(goal: FlightGoal) -> float | None:
    if goal.kind == "orbit" or (goal.kind == "part_test" and goal.situation == "orbiting"):
        return None
    if goal.kind == "suborbital" or (goal.kind == "part_test" and goal.situation == "sub_orbital"):
        return 70_000.0
    if goal.kind == "altitude":
        return goal.altitude_m or goal.altitude_max_m or goal.altitude_min_m
    if goal.kind == "part_test" and goal.situation == "flying":
        return goal.altitude_max_m or goal.altitude_min_m or 5_000.0
    return None


def _score(plan: ContractPlan) -> float:
    step = plan.steps[0]
    if step.kind == "part_test" and step.situation in {"landed", "splashed"}:
        return 2000.0
    if step.kind == "altitude":
        alt = step.altitude_m or step.altitude_min_m or 10_000.0
        return 1500.0 - alt / 100.0
    if step.kind == "part_test" and step.situation == "flying":
        return 1200.0 - (step.altitude_min_m or 0.0) / 100.0
    if step.kind == "suborbital" or (step.kind == "part_test" and step.situation == "sub_orbital"):
        return 800.0
    if step.kind == "orbit" or (step.kind == "part_test" and step.situation == "orbiting"):
        return 500.0
    if step.kind == "recover":
        return 200.0
    return 100.0


def _why(
    plan: ContractPlan,
    contract: ContractView,
    view: CareerView,
    skipped: Sequence[tuple[ContractView, str]],
) -> str:
    reward = _reward_phrase(contract)
    vessel = _vessel_phrase(view)
    passed = "; ".join(f"{item.title} ({reason})" for item, reason in skipped[:4])
    if len(skipped) > 4:
        passed = f"{passed}; and {len(skipped) - 4} more"
    passed_line = f" Passed over: {passed}." if passed else " Nothing else was offered."
    reward_line = f" {reward}." if reward else ""
    return (
        f"Accepted {plan.title!r} because {vessel}, and the steps are {_step_line(plan)}."
        f"{reward_line}{passed_line}"
    )


def _select_active(
    view: CareerView,
    memory: CareerMemory,
    body: str,
    notes: list[BoardNote],
) -> tuple[ContractPlan | None, ContractView | None]:
    chosen: tuple[ContractPlan, ContractView] | None = None
    for contract in view.active:
        if contract.key in memory.failed_keys or contract.key in memory.completed_keys:
            continue
        if contract.state in {"failed", "canceled", "deadline_expired", "completed"}:
            continue
        plan, reason = _assess(contract, view, body=body, committed=True)
        if plan is None:
            if contract.key not in memory.unparsed:
                memory.unparsed.add(contract.key)
                notes.append(
                    _note(
                        "discoveries",
                        f"career.unparsed.{_slug(contract.key)}",
                        {
                            "text": (
                                f"Active contract {contract.title!r} is not being flown: {reason}. "
                                "Not climbing as a stand-in for it."
                            ),
                            "action_id": None,
                            "contract_key": contract.key,
                        },
                        "agent",
                        "flight_engineer",
                    )
                )
            continue
        if contract.key == memory.accepted_key:
            return plan, contract
        if chosen is None:
            chosen = (plan, contract)
    if chosen is None:
        return None, None
    return chosen


def _fly_plan(
    memory: CareerMemory,
    notes: list[BoardNote],
    frame: Mapping[str, Any],
    plan: ContractPlan,
    contract: ContractView,
) -> CareerDirective:
    if _required_done(contract):
        if contract.key not in memory.completed_keys:
            memory.completed_keys.add(contract.key)
            memory.completed_titles[contract.key] = contract.title
            _reset_track(memory)
            done = (
                f"Contract {contract.title!r} is complete ({_step_line(plan)}). "
                "Turning it in where kRPC allows."
            )
            notes.append(
                _note(
                    "lessons",
                    f"career.done.{_slug(contract.key)}",
                    {
                        "text": done,
                        "ok": True,
                        "contract_key": contract.key,
                        "contract_title": contract.title,
                        "contract_type": contract.type,
                        "action_id": "ksp.contract.finish",
                    },
                    "agent",
                    "director",
                )
            )
        goal_line = f"Complete {contract.title}"
        if memory.goal_text != goal_line:
            memory.goal_text = goal_line
            notes.append(_goal_note(goal_line, contract.key))
        return CareerDirective(
            use_generic_fly=False,
            goal=_hold(
                f"{contract.title} is complete. Holding for turn-in.",
                key=contract.key,
                title=contract.title,
            ),
            actions=_finish_actions(memory, contract, "Parameters are complete."),
            notes=tuple(notes),
        )
    step = _current_step(plan, contract)
    if step is None:
        step = plan.steps[-1]
    goal_line = f"{contract.title}: {step.summary}"
    if memory.goal_text != goal_line:
        memory.goal_text = goal_line
        notes.append(_goal_note(goal_line, contract.key))
    actions: tuple[CareerAction, ...] = ()
    if step.kind == "recover" and _on_ground(frame):
        actions = _finish_actions(
            memory,
            contract,
            "The vessel is on the ground and the step is to recover it.",
        )
    return CareerDirective(use_generic_fly=False, goal=step, actions=actions, notes=tuple(notes))


def _current_step(plan: ContractPlan, contract: ContractView) -> FlightGoal | None:
    pending = [param.title for param in contract.parameters if not param.optional and not param.completed]
    if not pending:
        return None
    wanted = pending[0]
    for step in plan.steps:
        if step.parameter_title == wanted:
            return step
    return plan.steps[0]


def _required_done(contract: ContractView) -> bool:
    required = [param for param in contract.parameters if not param.optional]
    return bool(required) and all(param.completed and not param.failed for param in required)


def _flight_failure(
    frame: Mapping[str, Any],
    contract: ContractView,
    plan: ContractPlan,
    memory: CareerMemory,
) -> str | None:
    if _required_done(contract):
        return None
    step = _current_step(plan, contract)
    if step is None or _step_satisfied(frame, step):
        return None
    situation = _situation(frame)
    if (
        memory.saw_airborne
        and situation in {"landed", "splashed"}
        and not _ground_step(step)
        and memory.peak_alt > 400
    ):
        return f"the vessel was back on the ground at {_alt(frame) or 0:.0f} m before {step.summary} was done"
    if situation not in {"flying", "sub_orbital"}:
        return None
    view = career_from_frame(frame)
    if view is None:
        return None
    known = view.liquid_fuel is not None or view.oxidizer is not None or view.solid_fuel is not None
    total = (view.liquid_fuel or 0.0) + (view.oxidizer or 0.0) + (view.solid_fuel or 0.0)
    vertical = _vertical(frame)
    if known and total <= 0.05 and vertical is not None and vertical < 5 and step.kind != "recover":
        return f"out of fuel at {_alt(frame) or 0:.0f} m with {step.summary} still open"
    return None


def _step_satisfied(frame: Mapping[str, Any], step: FlightGoal) -> bool:
    alt = _alt(frame) or 0.0
    if step.kind == "altitude" and step.altitude_m is not None:
        return alt + 20 >= step.altitude_m
    if step.kind == "orbit" or (step.kind == "part_test" and step.situation == "orbiting"):
        apo = _orbit_value(frame, "apoapsis_m")
        peri = _orbit_value(frame, "periapsis_m")
        return apo is not None and peri is not None and apo >= 70_000 and peri >= 70_000
    if step.kind == "suborbital" or (step.kind == "part_test" and step.situation == "sub_orbital"):
        apo = _orbit_value(frame, "apoapsis_m")
        return apo is not None and apo >= 70_000
    if step.kind == "part_test" and step.situation in {"landed", "splashed"}:
        return _situation(frame) in {"landed", "splashed", "pre_launch"}
    if step.kind == "part_test" and step.situation == "flying":
        if step.altitude_min_m is not None and alt < step.altitude_min_m:
            return False
        if step.altitude_max_m is not None and alt > step.altitude_max_m:
            return False
        return _situation(frame) in {"flying", "sub_orbital"} and alt > 200
    return False


def _ground_step(step: FlightGoal) -> bool:
    if step.kind in {"recover", "hold"}:
        return True
    return step.kind == "part_test" and step.situation in {"landed", "splashed"}


def _mark_game_failures(memory: CareerMemory, notes: list[BoardNote], view: CareerView) -> None:
    for contract in view.active:
        if contract.state in {"failed", "deadline_expired", "canceled"}:
            _remember_failure(memory, notes, contract, f"the contract is {contract.state.replace('_', ' ')}")
            continue
        for param in contract.parameters:
            if param.failed and not param.optional:
                _remember_failure(memory, notes, contract, f"parameter failed: {param.title}")
                break


def _remember_failure(
    memory: CareerMemory,
    notes: list[BoardNote],
    contract: ContractView,
    reason: str,
) -> None:
    if contract.key == memory.accepted_key or contract.key == memory.goal_key:
        memory.chain_stopped = True
    if contract.key in memory.noted_failures:
        memory.failed_keys.add(contract.key)
        return
    memory.failed_keys.add(contract.key)
    memory.noted_failures.add(contract.key)
    if memory.accepted_key == contract.key:
        memory.accepted_key = None
        memory.accept_waits = 0
    text = f"Do not accept contract key `{contract.key}` ({contract.title}) again: {reason}."
    notes.append(
        _note(
            "lessons",
            f"career.fail.{_slug(contract.key)}",
            {
                "text": text,
                "ok": False,
                "contract_key": contract.key,
                "contract_title": contract.title,
                "contract_type": contract.type,
                "action_id": "ksp.contract.accept",
            },
            "agent",
            "director",
        )
    )


def _waiting_on_accept(
    memory: CareerMemory, view: CareerView, notes: list[BoardNote]
) -> Literal["wait", "miss", "ready"]:
    """``wait`` until the accepted contract is active. ``miss`` stops the chain."""
    key = memory.accepted_key
    if not key:
        return "ready"
    if key in memory.completed_keys:
        memory.accepted_key = None
        memory.accept_waits = 0
        return "ready"
    if any(contract.key == key for contract in view.active):
        memory.accept_waits = 0
        return "ready"
    offered = next((contract for contract in view.offered if contract.key == key), None)
    if offered is None:
        memory.accepted_key = None
        memory.accept_waits = 0
        return "ready"
    memory.accept_waits += 1
    if memory.accept_waits < _ACCEPT_WAIT_LIMIT:
        return "wait"
    _remember_failure(memory, notes, offered, "accepting it did not move it to active")
    return "miss"


def _finish_actions(memory: CareerMemory, contract: ContractView, why: str) -> tuple[CareerAction, ...]:
    if memory.finish_for != contract.key:
        memory.finish_for = contract.key
        memory.finish_ticks = 0
    memory.finish_ticks += 1
    if memory.finish_ticks != 1 and memory.finish_ticks % 4 != 0:
        return ()
    return (
        CareerAction(
            action_id="ksp.contract.finish",
            params={"type": contract.type, "title": contract.title},
            rationale=why,
            expected_effect=(
                "kRPC completes the contract, or recovers the vessel when that is the remaining step."
            ),
        ),
    )


def _idle_line(view: CareerView, failed: set[str], completed: set[str], body: str) -> str:
    if not view.offered and not view.active:
        return "No offered or active contracts. Not inventing a goal and not launching for one."
    reasons: list[str] = []
    for contract in view.offered:
        if contract.key in failed:
            reasons.append(f"{contract.title} (already failed)")
            continue
        if contract.key in completed:
            reasons.append(f"{contract.title} (already complete)")
            continue
        _plan, reason = _assess(contract, view, body=body, committed=False)
        reasons.append(f"{contract.title} ({reason})")
    listed = "; ".join(reasons[:4]) or "none are flyable"
    return (
        f"No offered contract this vessel can finish ({listed}). "
        "Not accepting one, and not climbing as a stand-in."
    )


def _track(memory: CareerMemory, key: str, frame: Mapping[str, Any]) -> None:
    if memory.goal_key != key:
        memory.goal_key = key
        memory.peak_alt = _alt(frame) or 0.0
        memory.saw_airborne = False
    alt = _alt(frame)
    if alt is not None:
        memory.peak_alt = max(memory.peak_alt, alt)
    if _situation(frame) in {"flying", "sub_orbital", "orbiting", "escaping"} and (alt or 0.0) > 150:
        memory.saw_airborne = True


def _reset_track(memory: CareerMemory) -> None:
    memory.goal_key = ""
    memory.peak_alt = 0.0
    memory.saw_airborne = False


def _goal(
    contract: ContractView,
    param: ContractParam,
    *,
    kind: str,
    summary: str,
    altitude_m: float | None = None,
    altitude_min_m: float | None = None,
    altitude_max_m: float | None = None,
    situation: str | None = None,
    part: str | None = None,
) -> FlightGoal:
    return FlightGoal(
        kind=kind,
        contract_key=contract.key,
        contract_title=contract.title,
        parameter_title=param.title,
        summary=summary,
        altitude_m=altitude_m,
        altitude_min_m=altitude_min_m,
        altitude_max_m=altitude_max_m,
        situation=situation,
        part=part,
    )


def _hold(summary: str, *, key: str = "", title: str = "") -> FlightGoal:
    return FlightGoal(
        kind="hold",
        contract_key=key,
        contract_title=title,
        parameter_title="",
        summary=summary,
    )


def _goal_note(text: str, key: str) -> BoardNote:
    return _note(
        "goals",
        "career.current",
        {"text": text, "contract_key": key},
        "director",
        "director",
    )


def _note(
    section: Literal["discoveries", "lessons", "goals", "notes"],
    key: str,
    value: dict[str, Any],
    kind: Literal["agent", "director"],
    author_id: str,
) -> BoardNote:
    return BoardNote(section=section, key=key, value=value, author_kind=kind, author_id=author_id)


def _contracts(raw: object) -> tuple[ContractView, ...]:
    if not isinstance(raw, list):
        return ()
    views: list[ContractView] = []
    for item in raw:
        if isinstance(item, dict):
            view = _contract(item)
            if view is not None:
                views.append(view)
    return tuple(views)


def _contract(raw: Mapping[str, Any]) -> ContractView | None:
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    contract_type = raw.get("type")
    state = raw.get("state")
    return ContractView(
        type=(
            contract_type.strip() if isinstance(contract_type, str) and contract_type.strip() else "contract"
        ),
        title=title.strip(),
        state=state.strip().lower() if isinstance(state, str) and state.strip() else "unknown",
        description=_text(raw.get("description")),
        synopsis=_text(raw.get("synopsis")),
        notes=_text(raw.get("notes")),
        funds_advance=_float(raw.get("funds_advance")),
        funds_completion=_float(raw.get("funds_completion")),
        funds_failure=_float(raw.get("funds_failure")),
        reputation_completion=_float(raw.get("reputation_completion")),
        reputation_failure=_float(raw.get("reputation_failure")),
        science_completion=_float(raw.get("science_completion")),
        parameters=_params(raw.get("parameters")),
    )


def _params(raw: object) -> tuple[ContractParam, ...]:
    if not isinstance(raw, list):
        return ()
    params: list[ContractParam] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        params.append(
            ContractParam(
                title=title.strip(),
                notes=_text(item.get("notes")),
                completed=bool(item.get("completed")),
                failed=bool(item.get("failed")),
                optional=bool(item.get("optional")),
            )
        )
    return tuple(params)


def _parts(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(item.strip() for item in raw if isinstance(item, str) and item.strip())


def _contract_phrases(contracts: Sequence[ContractView]) -> str:
    parts: list[str] = []
    for contract in contracts:
        params = "; ".join(
            f"{param.title} ({'done' if param.completed else 'failed' if param.failed else 'open'})"
            for param in contract.parameters
        )
        reward = _reward_phrase(contract)
        extra = f", {reward}" if reward else ""
        parts.append(f"{contract.title} [{contract.type}] — {params or 'no parameters'}{extra}")
    return " | ".join(parts)


def _reward_phrase(contract: ContractView) -> str:
    bits: list[str] = []
    if contract.funds_advance:
        bits.append(f"advance {contract.funds_advance:.0f} funds")
    if contract.funds_completion:
        bits.append(f"completion {contract.funds_completion:.0f} funds")
    if contract.science_completion:
        bits.append(f"{contract.science_completion:.0f} science")
    if contract.reputation_completion:
        bits.append(f"{contract.reputation_completion:.0f} reputation")
    return ", ".join(bits)


def _economy_phrase(view: CareerView) -> str:
    bits: list[str] = []
    if view.funds is not None:
        bits.append(f"funds {view.funds:.0f}")
    if view.science is not None:
        bits.append(f"science {view.science:.0f}")
    if view.reputation is not None:
        bits.append(f"reputation {view.reputation:.0f}")
    if not bits:
        return f"{(view.mode or 'career').title()}. "
    return f"{(view.mode or 'career').title()} ({', '.join(bits)}). "


def _vessel_phrase(view: CareerView) -> str:
    bits: list[str] = []
    if view.liquid_fuel is not None:
        bits.append(f"liquid fuel {view.liquid_fuel:.0f}")
    if view.oxidizer is not None:
        bits.append(f"oxidizer {view.oxidizer:.0f}")
    if view.solid_fuel is not None:
        bits.append(f"solid fuel {view.solid_fuel:.0f}")
    if view.parts:
        bits.append(f"{len(view.parts)} parts on the vessel")
    if not bits:
        return "the vessel can reach the step"
    return "the vessel shows " + ", ".join(bits)


def _step_line(plan: ContractPlan) -> str:
    return "; then ".join(step.summary for step in plan.steps)


def _title_for(view: CareerView, key: str | None) -> str | None:
    if not key:
        return None
    for contract in (*view.offered, *view.active):
        if contract.key == key:
            return contract.title
    return None


def _situation_phrase(text: str) -> str | None:
    if re.search(r"sub-?orbital", text, re.IGNORECASE):
        return "sub_orbital"
    if re.search(r"\blanded\b", text, re.IGNORECASE):
        return "landed"
    if re.search(r"\bsplashed\b", text, re.IGNORECASE):
        return "splashed"
    if re.search(r"in orbit|while orbiting|\borbiting\b", text, re.IGNORECASE):
        return "orbiting"
    if re.search(r"\bescaping\b", text, re.IGNORECASE):
        return "escaping"
    if re.search(r"in flight|\bflying\b", text, re.IGNORECASE):
        return "flying"
    return None


def _foreign(text: str, current: str) -> str | None:
    here = (current or "Kerbin").strip().lower() or "kerbin"
    for body in _BODIES:
        if body == here:
            continue
        if re.search(rf"\b{re.escape(body)}\b", text, re.IGNORECASE):
            return body
    return None


def _meters(text: str) -> list[float]:
    found: list[float] = []
    for match in _METERS.finditer(text):
        number = float(match.group(1).replace(",", ""))
        if match.group(2).lower() == "km":
            number *= 1000.0
        found.append(number)
    return found


def _on_ground(frame: Mapping[str, Any]) -> bool:
    return _situation(frame) in {"landed", "splashed", "pre_launch"}


def _situation(frame: Mapping[str, Any]) -> str | None:
    vehicle = frame.get("vehicle")
    if not isinstance(vehicle, dict):
        return None
    raw = vehicle.get("situation")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _alt(frame: Mapping[str, Any]) -> float | None:
    vehicle = frame.get("vehicle")
    if not isinstance(vehicle, dict):
        return None
    geo = vehicle.get("geo")
    if not isinstance(geo, dict):
        return None
    return _float(geo.get("alt_m"))


def _vertical(frame: Mapping[str, Any]) -> float | None:
    vehicle = frame.get("vehicle")
    if not isinstance(vehicle, dict):
        return None
    velocity = vehicle.get("velocity")
    if not isinstance(velocity, dict):
        return None
    return _float(velocity.get("vertical_mps"))


def _orbit_value(frame: Mapping[str, Any], name: str) -> float | None:
    vehicle = frame.get("vehicle")
    if not isinstance(vehicle, dict):
        return None
    orbit = vehicle.get("orbit")
    if not isinstance(orbit, dict):
        return None
    return _float(orbit.get(name))


def _norm(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "contract"
