"""`GameEvent` (Section 7.4), the record on `titan:s:{sid}:events` and the `game.event` payload."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from titan_core.protocol.common import EventCategory, MarkerKind, ProtocolModel, Ratio, Severity


class EventMarker(ProtocolModel):
    kind: MarkerKind
    duration_ms: int = Field(ge=0)


class GameEvent(ProtocolModel):
    id: UUID
    session_id: UUID
    seq: int = Field(ge=0, description="Per-session, monotonically increasing")
    type: str = Field(description="'<game>.<name>' or 'vehicle.<name>' for shared rules")
    category: EventCategory
    severity: Severity
    salience: Ratio = Field(description="0..1, drives commentary urgency and highlight scoring")
    source: str = Field(description="'rule:ksp.max_q' | 'adapter:scs' | 'capture'")
    t_mono_ns: int
    t_session_ms: int
    occurred_at: datetime
    frame_seq: int | None
    payload: dict[str, Any]
    marker: EventMarker | None = None
