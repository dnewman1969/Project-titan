"""Map game events to low-risk play proposals (learn-and-play beta)."""

from __future__ import annotations

from typing import Any

from titan_core.protocol.events import GameEvent


def play_proposal_for_event(event: GameEvent) -> dict[str, Any] | None:
    """Return an ActionPropose-shaped dict when the crew should adjust controls."""
    if event.type == "ksp.launch":
        return {
            "action_id": "ksp.throttle",
            "params": {"throttle": 0.75},
            "rationale": "Maintain climb after launch — throttle to three-quarters.",
            "risk": "low",
            "expected_effect": "Continued ascent without excessive dynamic pressure.",
        }
    if event.type == "ksp.staging":
        return {
            "action_id": "ksp.throttle",
            "params": {"throttle": 0.55},
            "rationale": "Hold steady thrust after staging.",
            "risk": "low",
            "expected_effect": "Smooth acceleration through the next ascent phase.",
        }
    if event.type == "ksp.max_q":
        return {
            "action_id": "ksp.throttle",
            "params": {"throttle": 0.35},
            "rationale": "Ease through max-Q.",
            "risk": "low",
            "expected_effect": "Lower dynamic pressure through the critical window.",
        }
    if event.type in {"ets2.collision", "scs.hard_brake"}:
        return {
            "action_id": "scs.brake",
            "params": {"fraction": 0.6},
            "rationale": "Recover from instability.",
            "risk": "medium",
            "expected_effect": "Vehicle slows to a safe speed.",
        }
    return None
