"""Shared building blocks for protocol models."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Json = Any
"""Arbitrary JSON value (TypeScript `Json`)."""

JsonObject = dict[str, Any]

Ratio = Annotated[float, Field(ge=0, le=1)]
"""A number between 0 and 1."""

Section = Literal[
    "goals", "plan", "tasks", "world_state", "facts", "hypotheses", "risks", "discoveries", "lessons", "notes"
]
"""Blackboard sections (Section 6.4, `blackboard_entries.section`)."""

TaskKind = Literal["analyze", "plan", "monitor", "explain", "compute", "summarize"]
AgentState = Literal["spawning", "ready", "busy", "paused", "terminating", "terminated", "crashed"]
MissionStatus = Literal["planned", "active", "succeeded", "failed", "abandoned"]
Severity = Literal["debug", "info", "notice", "warning", "critical"]
EventCategory = Literal["game", "agent", "system", "user", "safety", "recording"]
MarkerKind = Literal[
    "highlight",
    "achievement",
    "failure",
    "funny",
    "tension",
    "emotional",
    "mission_complete",
    "chapter",
    "user",
]
Domain = Literal["space", "ground_vehicle", "aircraft", "naval", "strategy", "other"]
SessionState = Literal["created", "starting", "live", "paused", "stopping", "ended", "failed"]
SessionOutcome = Literal["success", "partial", "failure", "aborted"]
ControlOwner = Literal["none", "ai", "human"]


class ProtocolModel(BaseModel):
    """Base for every wire model: unknown fields are rejected, aliases are used on the wire."""

    model_config = ConfigDict(
        extra="forbid",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    def to_wire(self) -> JsonObject:
        """JSON-compatible dict, omitting optional fields that were never set."""
        return self.model_dump(mode="json", exclude_unset=True)
