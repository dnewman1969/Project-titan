"""The bus `Envelope` (Section 6.1). Every message on `titan:s:{sid}:bus` is one of these."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from titan_core.clock import mono_ns, utc_now
from titan_core.ids import uuid7
from titan_core.protocol.common import JsonObject, ProtocolModel

ENVELOPE_SCHEMA = "titan.msg/1"
MAX_ENVELOPE_BYTES = 32 * 1024
"""Section 6.3: larger data goes on the blackboard or in files."""

TYPE_PATTERN = r"^[a-z]+(\.[a-z_]+)+$"
RECIPIENT_PATTERN = (
    r"^(broadcast|director|instance:[0-9a-f-]{36}|role:[a-z_]+|team:[a-z_]+"
    r"|persona:[a-z0-9_.-]+|user|system)$"
)

Recipient = Annotated[str, Field(pattern=RECIPIENT_PATTERN)]
Visibility = Literal["public", "internal"]


class Address(ProtocolModel):
    kind: Literal["agent", "director", "system", "user", "adapter", "safety"]
    id: str = Field(description="instance uuid, 'director', 'system', 'user', adapter slug")
    role: str | None = None
    persona_slug: str | None = None


class Envelope(ProtocolModel):
    id: UUID = Field(description="UUIDv7")
    schema_: Literal["titan.msg/1"] = Field(alias="schema")
    type: str = Field(pattern=TYPE_PATTERN)
    session_id: UUID
    mission_id: UUID | None = None
    ts: datetime
    t_mono_ns: int
    sender: Address
    recipients: list[Recipient] = Field(min_length=1)
    correlation_id: UUID | None = Field(default=None, description="Conversation/task thread id")
    causation_id: UUID | None = Field(default=None, description="Envelope that caused this one")
    reply_to: UUID | None = None
    visibility: Visibility = Field(description="public = shown in Agents panel")
    priority: int = Field(ge=0, le=9, description="9 = highest")
    ttl_ms: int | None = Field(default=None, ge=0)
    payload: JsonObject = Field(description="Schema selected by `type` (Sec 6.2)")


def make_envelope(
    *,
    type: str,
    session_id: UUID,
    sender: Address,
    recipients: list[str],
    visibility: Visibility,
    priority: int,
    payload: JsonObject | ProtocolModel,
    mission_id: UUID | None = None,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    reply_to: UUID | None = None,
    ttl_ms: int | None = None,
) -> Envelope:
    """Create an envelope stamped with a fresh UUIDv7, wall time and monotonic time."""
    body = payload.to_wire() if isinstance(payload, ProtocolModel) else payload
    optional = {
        "mission_id": mission_id,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "reply_to": reply_to,
        "ttl_ms": ttl_ms,
    }
    return Envelope.model_validate(
        {
            "id": uuid7(),
            "schema": ENVELOPE_SCHEMA,
            "type": type,
            "session_id": session_id,
            "ts": utc_now(),
            "t_mono_ns": mono_ns(),
            "sender": sender,
            "recipients": recipients,
            "visibility": visibility,
            "priority": priority,
            "payload": body,
            **{k: v for k, v in optional.items() if v is not None},
        }
    )
