"""Director task lifecycle state machine (Section 6.5, M6.T4)."""

from __future__ import annotations

from typing import Literal

TaskState = Literal[
    "proposed",
    "assigned",
    "accepted",
    "in_progress",
    "blocked",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
]

TERMINAL: frozenset[TaskState] = frozenset({"completed", "failed", "cancelled", "timed_out"})

_TRANSITIONS: dict[tuple[TaskState, str], TaskState] = {
    ("proposed", "assign"): "assigned",
    ("assigned", "accept"): "accepted",
    ("assigned", "reject"): "proposed",
    ("assigned", "timeout"): "proposed",
    ("accepted", "start"): "in_progress",
    ("in_progress", "complete"): "completed",
    ("in_progress", "fail"): "failed",
    ("in_progress", "block"): "blocked",
    ("blocked", "unblock"): "in_progress",
    ("accepted", "timeout"): "timed_out",
    ("in_progress", "timeout"): "timed_out",
    ("blocked", "timeout"): "timed_out",
    ("failed", "retry"): "proposed",
    ("timed_out", "retry"): "proposed",
}


def transition(current: TaskState, event: str) -> TaskState:
    key = (current, event)
    if key not in _TRANSITIONS:
        msg = f"invalid transition {current!r} + {event!r}"
        raise ValueError(msg)
    return _TRANSITIONS[key]


def cancel(current: TaskState) -> TaskState:
    if current in TERMINAL:
        msg = f"cannot cancel terminal state {current!r}"
        raise ValueError(msg)
    return "cancelled"


def is_terminal(state: TaskState) -> bool:
    return state in TERMINAL
