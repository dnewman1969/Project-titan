"""Map game events to low-risk play proposals (learn-and-play beta)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from titan_core.protocol.events import GameEvent

# Recent failed action_ids - suppress identical proposals until a success clears them.
_FAILED_ACTION_LIMIT = 32


@dataclass
class PlayMemory:
    """Session-local memory so the crew adapts after failed play attempts."""

    failed_actions: deque[str] = field(default_factory=lambda: deque(maxlen=_FAILED_ACTION_LIMIT))
    success_counts: dict[str, int] = field(default_factory=dict)
    fail_counts: dict[str, int] = field(default_factory=dict)
    last_action_by_proposal: dict[str, str] = field(default_factory=dict)

    def remember_proposal(self, proposal_id: str, action_id: str) -> None:
        self.last_action_by_proposal[proposal_id] = action_id

    def record_outcome(
        self, *, proposal_id: str | None, ok: bool, action_id: str | None = None
    ) -> str | None:
        resolved = action_id
        if resolved is None and proposal_id:
            resolved = self.last_action_by_proposal.pop(proposal_id, None)
        elif proposal_id:
            self.last_action_by_proposal.pop(proposal_id, None)
        if not resolved:
            return None
        if ok:
            self.success_counts[resolved] = self.success_counts.get(resolved, 0) + 1
            while resolved in self.failed_actions:
                self.failed_actions.remove(resolved)
        else:
            self.fail_counts[resolved] = self.fail_counts.get(resolved, 0) + 1
            self.failed_actions.append(resolved)
        return resolved

    def should_skip(self, action_id: str) -> bool:
        # Skip if the last two outcomes for this action failed without a later success.
        fails = self.fail_counts.get(action_id, 0)
        wins = self.success_counts.get(action_id, 0)
        return fails >= 2 and fails > wins


_SESSION_MEMORY: dict[str, PlayMemory] = {}


def play_memory_for(session_id: str) -> PlayMemory:
    mem = _SESSION_MEMORY.get(session_id)
    if mem is None:
        mem = PlayMemory()
        _SESSION_MEMORY[session_id] = mem
    return mem


def clear_play_memory(session_id: str | None = None) -> None:
    if session_id is None:
        _SESSION_MEMORY.clear()
    else:
        _SESSION_MEMORY.pop(session_id, None)


def _base_proposal(event: GameEvent) -> dict[str, Any] | None:
    if event.type == "ksp.launch":
        return {
            "action_id": "ksp.throttle",
            "params": {"throttle": 0.75},
            "rationale": "Maintain climb after launch - throttle to three-quarters.",
            "risk": "low",
            "expected_effect": "Continued ascent without excessive dynamic pressure.",
        }
    if event.type == "ksp.staging":
        return {
            "action_id": "ksp.stage",
            "params": {},
            "rationale": "Stage when the booster is empty.",
            "risk": "medium",
            "expected_effect": "Next stage ignites for continued ascent.",
        }
    if event.type == "ksp.max_q":
        return {
            "action_id": "ksp.throttle",
            "params": {"throttle": 0.35},
            "rationale": "Ease through max-Q.",
            "risk": "low",
            "expected_effect": "Lower dynamic pressure through the critical window.",
        }
    if event.type in {"ksp.apoapsis", "ksp.orbit_achieved"}:
        return {
            "action_id": "ksp.throttle",
            "params": {"throttle": 0.0},
            "rationale": "Coast after apoapsis / orbit - cut throttle.",
            "risk": "low",
            "expected_effect": "Engines idle while the trajectory settles.",
        }
    if event.type == "ksp.landing":
        return {
            "action_id": "ksp.brake",
            "params": {"enabled": True},
            "rationale": "Deploy brakes / airbrakes for landing.",
            "risk": "low",
            "expected_effect": "Slower descent for a safer touchdown.",
        }
    if event.type in {"ets2.collision", "scs.hard_brake", "ats.collision"}:
        return {
            "action_id": "scs.brake",
            "params": {"fraction": 0.6},
            "rationale": "Recover from instability.",
            "risk": "medium",
            "expected_effect": "Vehicle slows to a safe speed.",
        }
    if event.type in {"ets2.overspeed", "ats.overspeed", "scs.overspeed"}:
        return {
            "action_id": "scs.throttle",
            "params": {"throttle": 0.2},
            "rationale": "Ease off the throttle after overspeed.",
            "risk": "low",
            "expected_effect": "Speed drops toward the limit.",
        }
    return None


def _adapt_after_failures(proposal: dict[str, Any], memory: PlayMemory) -> dict[str, Any] | None:
    action_id = str(proposal["action_id"])
    if not memory.should_skip(action_id):
        return proposal
    # After repeated throttle failures, try a gentler setting once more with a new rationale.
    if action_id == "ksp.throttle":
        params = dict(proposal.get("params") or {})
        raw = params.get("throttle", 0.5)
        current = float(raw if raw is not None else 0.5)
        gentler = max(0.0, min(1.0, current * 0.5))
        if gentler == current:
            return None
        adapted = dict(proposal)
        adapted["params"] = {**params, "throttle": gentler}
        adapted["rationale"] = (
            f"Prior throttle attempts failed - retrying at {gentler:.2f} (was {current:.2f})."
        )
        return adapted
    if action_id == "scs.brake":
        params = dict(proposal.get("params") or {})
        raw = params.get("fraction", params.get("brake", 0.6))
        fraction = float(raw if raw is not None else 0.6)
        stronger = min(1.0, fraction + 0.2)
        if stronger == fraction:
            return None
        adapted = dict(proposal)
        adapted["params"] = {**params, "fraction": stronger}
        adapted["rationale"] = f"Prior brake was weak - applying stronger brake ({stronger:.2f})."
        return adapted
    return None


def play_proposal_for_event(
    event: GameEvent,
    *,
    session_id: str | None = None,
    memory: PlayMemory | None = None,
) -> dict[str, Any] | None:
    """Return an ActionPropose-shaped dict when the crew should adjust controls."""
    proposal = _base_proposal(event)
    if proposal is None:
        return None
    mem = memory
    if mem is None and session_id is not None:
        mem = play_memory_for(session_id)
    if mem is None:
        return proposal
    return _adapt_after_failures(proposal, mem)
