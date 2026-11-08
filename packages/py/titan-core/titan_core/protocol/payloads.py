"""Envelope payloads selected by `Envelope.type` (Section 6.2).

`MESSAGE_TYPES` maps every Phase 1 message type to its payload model. Action payloads are
frozen now and rejected by `titan-actions` until Phase 4.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from titan_core.protocol.common import (
    AgentState,
    Json,
    MissionStatus,
    ProtocolModel,
    Ratio,
    Section,
    TaskKind,
)
from titan_core.protocol.envelope import Envelope
from titan_core.protocol.events import GameEvent


class BBRef(ProtocolModel):
    section: Section
    key: str
    version: int = Field(ge=1)


# ---- Tasks (Director <-> agents)
class TaskAssign(ProtocolModel):
    task_id: UUID
    kind: TaskKind
    title: str
    input: Json
    mission_id: UUID | None = None
    deadline_ms: int = Field(ge=0)
    priority: int = Field(ge=0, le=9)
    acceptance: str = Field(description='What "done" means')


class TaskAccept(ProtocolModel):
    task_id: UUID
    eta_ms: int | None = Field(default=None, ge=0)


class TaskReject(ProtocolModel):
    task_id: UUID
    reason: Literal["busy", "out_of_scope", "missing_input", "unsafe"]
    detail: str | None = None


class TaskProgress(ProtocolModel):
    task_id: UUID
    progress: Ratio
    note: str | None = None


class TaskBlocked(ProtocolModel):
    task_id: UUID
    needs: str
    from_role: str | None = None


class TaskComplete(ProtocolModel):
    task_id: UUID
    output: Json
    summary: str
    bb_refs: list[BBRef]


class TaskFail(ProtocolModel):
    task_id: UUID
    reason: str
    retryable: bool


class TaskCancel(ProtocolModel):
    task_id: UUID
    reason: str


class TaskEvaluate(ProtocolModel):
    task_id: UUID
    score: Ratio
    notes: str


# ---- Blackboard notifications
class BBWritten(ProtocolModel):
    section: Section
    key: str
    version: int = Field(ge=1)
    op: Literal["put", "retract"]
    bb_version: int = Field(ge=0)


class ConflictRaised(ProtocolModel):
    section: Section
    key: str
    versions: list[int]
    authors: list[str]
    summary: str


# ---- Queries between agents
class QueryAsk(ProtocolModel):
    question: str
    context_refs: list[BBRef] | None = None


class QueryAnswer(ProtocolModel):
    answer: str
    confidence: Ratio
    bb_refs: list[BBRef] | None = None


# ---- Conversation
class ChatSay(ProtocolModel):
    text: str
    kind: Literal["say", "aside"]
    event_ref: UUID | None = None
    mentions: list[str] | None = None
    tokens: int | None = Field(default=None, ge=0)
    model: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class ChatDelta(ProtocolModel):
    message_id: UUID
    delta: str


class UserSay(ProtocolModel):
    text: str
    to: list[str]


# ---- Floor control
class FloorRequest(ProtocolModel):
    urgency: Ratio
    topic: str
    event_ref: UUID | None = None
    est_words: int = Field(ge=0)


class FloorGrant(ProtocolModel):
    request_id: UUID
    max_words: int = Field(gt=0)
    deadline_ms: int = Field(ge=0)


class FloorDeny(ProtocolModel):
    request_id: UUID
    reason: Literal["busy", "cooldown", "low_urgency", "muted", "stale"]


class FloorRelease(ProtocolModel):
    request_id: UUID
    spoke: bool


class FloorPreempt(ProtocolModel):
    holder: str
    reason: Literal["critical_event", "user_speaking", "kill"]


# ---- Lifecycle
class AgentSpawn(ProtocolModel):
    agent_id: UUID
    instance_id: UUID
    reason: str


class AgentReady(ProtocolModel):
    instance_id: UUID
    model: str
    tools: list[str]


class AgentHeartbeat(ProtocolModel):
    instance_id: UUID
    state: AgentState
    inbox_depth: int = Field(ge=0)
    open_tasks: int = Field(ge=0)


class AgentTerminate(ProtocolModel):
    instance_id: UUID
    reason: Literal["session_end", "director_retire", "user", "crash_loop", "resource_guard"]
    grace_ms: int = Field(ge=0)


class AgentTerminated(ProtocolModel):
    instance_id: UUID
    reason: str
    final_report: str | None = None


# ---- Game and world
class WorldStateTick(ProtocolModel):
    bb_version: int = Field(ge=0)
    scene: str
    summary: Json


# ---- Actions (P4; schema frozen now)
class ActionPropose(ProtocolModel):
    action_id: str
    params: Json
    rationale: str
    risk: Literal["low", "medium", "high", "irreversible"]
    expected_effect: str


class ActionDecision(ProtocolModel):
    proposal_id: UUID
    decision: Literal["approved", "denied"]
    by: Literal["director", "policy", "user"]
    reason: str | None = None


class ActionExecuted(ProtocolModel):
    proposal_id: UUID
    ok: bool
    latency_ms: int = Field(ge=0)
    error: str | None = None


# ---- Safety
class SafetyKill(ProtocolModel):
    source: Literal["hotkey", "ui", "api", "watchdog", "policy"]
    detail: str | None = None


class SafetyOverride(ProtocolModel):
    control_owner: Literal["human", "ai", "none"]
    reason: str


class SafetyResume(ProtocolModel):
    by: Literal["user"]


# ---- Session
class MissionUpdate(ProtocolModel):
    mission_id: UUID
    status: MissionStatus
    note: str | None = None


class DirectorReport(ProtocolModel):
    period_s: int = Field(ge=0)
    goals: list[str]
    progress: str
    issues: list[str]
    next: list[str]


MESSAGE_TYPES: dict[str, type[ProtocolModel]] = {
    "task.assign": TaskAssign,
    "task.accept": TaskAccept,
    "task.reject": TaskReject,
    "task.progress": TaskProgress,
    "task.blocked": TaskBlocked,
    "task.complete": TaskComplete,
    "task.fail": TaskFail,
    "task.cancel": TaskCancel,
    "task.evaluate": TaskEvaluate,
    "bb.written": BBWritten,
    "conflict.raised": ConflictRaised,
    "query.ask": QueryAsk,
    "query.answer": QueryAnswer,
    "chat.say": ChatSay,
    "chat.delta": ChatDelta,
    "user.say": UserSay,
    "floor.request": FloorRequest,
    "floor.grant": FloorGrant,
    "floor.deny": FloorDeny,
    "floor.release": FloorRelease,
    "floor.preempt": FloorPreempt,
    "agent.spawn": AgentSpawn,
    "agent.ready": AgentReady,
    "agent.heartbeat": AgentHeartbeat,
    "agent.terminate": AgentTerminate,
    "agent.terminated": AgentTerminated,
    "game.event": GameEvent,
    "world.tick": WorldStateTick,
    "action.propose": ActionPropose,
    "action.decision": ActionDecision,
    "action.executed": ActionExecuted,
    "safety.kill": SafetyKill,
    "safety.override": SafetyOverride,
    "safety.resume": SafetyResume,
    "mission.update": MissionUpdate,
    "director.report": DirectorReport,
}


class UnknownMessageType(ValueError):
    pass


def parse_payload(envelope: Envelope) -> ProtocolModel:
    """Validate `envelope.payload` against the model registered for `envelope.type`."""
    model = MESSAGE_TYPES.get(envelope.type)
    if model is None:
        raise UnknownMessageType(envelope.type)
    return model.model_validate(envelope.payload)
