from __future__ import annotations

import pytest

from titan_orchestrator.director.tasks import cancel, is_terminal, transition


def test_task_lifecycle_happy_path() -> None:
    state = "proposed"
    state = transition(state, "assign")
    assert state == "assigned"
    state = transition(state, "accept")
    assert state == "accepted"
    state = transition(state, "start")
    assert state == "in_progress"
    state = transition(state, "complete")
    assert state == "completed"
    assert is_terminal(state)


def test_task_reject_returns_to_proposed() -> None:
    state = transition("assigned", "reject")
    assert state == "proposed"


def test_cancel_from_non_terminal() -> None:
    assert cancel("in_progress") == "cancelled"


def test_invalid_transition_raises() -> None:
    with pytest.raises(ValueError):
        transition("completed", "assign")
