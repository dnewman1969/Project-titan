"""Session loop helpers."""

from __future__ import annotations

from titan_core.protocol.events import GameEvent
from titan_orchestrator.session_loops import _event_line


def test_event_line_salience_bands() -> None:
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "seq": 1,
        "type": "ksp.staging",
        "category": "game",
        "severity": "info",
        "source": "rule:test",
        "t_mono_ns": 1,
        "t_session_ms": 1,
        "occurred_at": "2026-01-01T00:00:00Z",
        "frame_seq": 1,
        "payload": {},
    }
    high = GameEvent.model_validate({**base, "salience": 0.9})
    mid = GameEvent.model_validate({**base, "salience": 0.6})
    low = GameEvent.model_validate({**base, "salience": 0.2})
    assert "Critical" in _event_line(high)
    assert "Noted" in _event_line(mid)
    assert "Saw" in _event_line(low)
