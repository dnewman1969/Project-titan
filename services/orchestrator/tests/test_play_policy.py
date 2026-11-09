"""Play policy mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from titan_core.protocol.events import GameEvent
from titan_orchestrator.play_policy import play_proposal_for_event


def _event(type_: str) -> GameEvent:
    return GameEvent.model_validate(
        {
            "id": UUID(int=0),
            "session_id": UUID(int=1),
            "seq": 1,
            "type": type_,
            "category": "game",
            "severity": "info",
            "salience": 0.7,
            "source": "rule:test",
            "t_mono_ns": 1,
            "t_session_ms": 1,
            "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
            "frame_seq": 1,
            "payload": {},
        }
    )


def test_ksp_launch_proposal() -> None:
    proposal = play_proposal_for_event(_event("ksp.launch"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.throttle"


def test_unrelated_event_returns_none() -> None:
    assert play_proposal_for_event(_event("ksp.menu_open")) is None


def test_staging_proposal() -> None:
    proposal = play_proposal_for_event(_event("ksp.staging"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.stage"


def test_max_q_throttle_cut() -> None:
    proposal = play_proposal_for_event(_event("ksp.max_q"))
    assert proposal is not None
    assert proposal["params"]["throttle"] < 0.5
