"""Play policy mapping and learn memory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from titan_core.protocol.events import GameEvent
from titan_orchestrator.play_policy import (
    PlayMemory,
    clear_play_memory,
    play_proposal_for_event,
)


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
    clear_play_memory()
    proposal = play_proposal_for_event(_event("ksp.launch"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.throttle"


def test_unrelated_event_returns_none() -> None:
    assert play_proposal_for_event(_event("ksp.menu_open")) is None


def test_staging_proposal() -> None:
    proposal = play_proposal_for_event(_event("ksp.staging"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.stage"


def test_max_q_starts_gravity_turn_steer() -> None:
    proposal = play_proposal_for_event(_event("ksp.max_q"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.steer"
    assert float(proposal["params"]["pitch"]) < 0


def test_orbit_cuts_throttle() -> None:
    proposal = play_proposal_for_event(_event("ksp.orbit_achieved"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.throttle"
    assert proposal["params"]["throttle"] == 0.0


def test_landing_deploys_gear() -> None:
    proposal = play_proposal_for_event(_event("ksp.landed"))
    assert proposal is not None
    assert proposal["action_id"] == "ksp.gear"
    assert proposal["params"]["deployed"] is True


def test_overspeed_eases_throttle() -> None:
    proposal = play_proposal_for_event(_event("ets2.overspeed"))
    assert proposal is not None
    assert proposal["action_id"] == "scs.throttle"


def test_memory_adapts_after_repeated_failures() -> None:
    mem = PlayMemory()
    first = play_proposal_for_event(_event("ksp.launch"), memory=mem)
    assert first is not None
    mem.remember_proposal("p1", "ksp.throttle")
    mem.record_outcome(proposal_id="p1", ok=False)
    mem.remember_proposal("p2", "ksp.throttle")
    mem.record_outcome(proposal_id="p2", ok=False)
    adapted = play_proposal_for_event(_event("ksp.launch"), memory=mem)
    assert adapted is not None
    assert adapted["params"]["throttle"] < first["params"]["throttle"]
    assert "Prior throttle" in adapted["rationale"]
