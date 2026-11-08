"""WebSocket protocol frames and channel payloads (Section 5.3).

One connection at `ws://127.0.0.1:8765/api/v1/ws`. The first client frame must be `auth`
within 3 s or the server closes with `CLOSE_UNAUTHORIZED`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, RootModel

from titan_core.protocol.common import (
    AgentState,
    ControlOwner,
    ProtocolModel,
    SessionOutcome,
    SessionState,
)
from titan_core.protocol.events import GameEvent
from titan_core.protocol.telemetry import TelemetryFrameUI

WS_PATH = "/api/v1/ws"
AUTH_TIMEOUT_S = 3
SEND_BUFFER_FRAMES = 512
CLOSE_UNAUTHORIZED = 4401
CLOSE_BACKPRESSURE = 4408


# ---------------------------------------------------------------- client -> server
class AuthFrame(ProtocolModel):
    op: Literal["auth"]
    token: str
    client: str = Field(description="e.g. 'desktop/1.0.0'")


class SubscribeOptions(ProtocolModel):
    full: bool | None = Field(default=None, description="Include telemetry game_specific")


class SubscribeFrame(ProtocolModel):
    op: Literal["subscribe"]
    req_id: str
    channel: str
    since_seq: str | None = Field(default=None, description="Last seen Redis stream id")
    options: SubscribeOptions | None = None


class UnsubscribeFrame(ProtocolModel):
    op: Literal["unsubscribe"]
    req_id: str
    channel: str


class PingFrame(ProtocolModel):
    op: Literal["ping"]
    req_id: str


class ClientFrame(
    RootModel[Annotated[AuthFrame | SubscribeFrame | UnsubscribeFrame | PingFrame, Field(discriminator="op")]]
):
    """Any frame the client may send."""


# ---------------------------------------------------------------- server -> client
class AckError(ProtocolModel):
    code: str
    detail: str


class AckFrame(ProtocolModel):
    op: Literal["ack"]
    req_id: str
    ok: bool
    error: AckError | None = None


class MsgFrame(ProtocolModel):
    op: Literal["msg"]
    channel: str
    seq: str = Field(description="Redis stream id")
    ts: datetime
    type: str
    data: dict[str, Any]


class PongFrame(ProtocolModel):
    op: Literal["pong"]
    req_id: str


class GapFrame(ProtocolModel):
    op: Literal["gap"]
    channel: str
    from_seq: str
    reason: str


class ServerFrame(
    RootModel[Annotated[AckFrame | MsgFrame | PongFrame | GapFrame, Field(discriminator="op")]]
):
    """Any frame the server may send."""


# ---------------------------------------------------------------- channel `data` shapes
class ChatSender(ProtocolModel):
    instance_id: UUID
    persona_slug: str
    display_name: str
    role: str
    color_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    portrait_url: str | None


class ChatStartData(ProtocolModel):
    message_id: UUID
    sender: ChatSender
    reply_to: UUID | None
    event_ref: UUID | None
    kind: Literal["say"]


class ChatDeltaData(ProtocolModel):
    message_id: UUID
    delta: str


class ChatFinalData(ProtocolModel):
    message_id: UUID
    text: str
    tokens: int = Field(ge=0)
    model: str
    latency_ms: int = Field(ge=0)
    mentions: list[str]


class ChatCancelledData(ProtocolModel):
    message_id: UUID
    reason: str


class UserSayData(ProtocolModel):
    message_id: UUID
    text: str
    to: list[str]


class SystemNoticeData(ProtocolModel):
    text: str
    level: Literal["info", "warning", "error"]


class AgentStateData(ProtocolModel):
    instance_id: UUID
    state: AgentState
    reason: str | None = None


class TaskUpdateData(ProtocolModel):
    task_id: UUID
    state: str
    assignee_instance_id: UUID | None
    title: str


class FloorStateData(ProtocolModel):
    holder_instance_id: UUID | None
    queue: list[UUID]


class BBUpdateData(ProtocolModel):
    section: str
    key: str
    version: int = Field(ge=1)
    author: str


class SessionStateData(ProtocolModel):
    state: SessionState
    outcome: SessionOutcome | None = None


class SessionEndedData(ProtocolModel):
    report_url: str


class RecordingTrackStatus(ProtocolModel):
    kind: str
    state: str
    bytes: int | None = Field(default=None, ge=0)
    bitrate_kbps: float | None = None
    dropped_frames: int | None = Field(default=None, ge=0)
    fps: float | None = None
    level_dbfs: float | None = None


class RecordingStatus(ProtocolModel):
    recording_id: UUID
    state: str
    elapsed_ms: int = Field(ge=0)
    obs_connected: bool
    disk_free_bytes: int = Field(ge=0)
    est_remaining_min: int | None
    tracks: list[RecordingTrackStatus]


class GpuMetrics(ProtocolModel):
    index: int = Field(ge=0)
    name: str
    util_pct: float | None
    vram_used_mb: int | None
    vram_total_mb: int | None
    temp_c: float | None
    encoder_util_pct: float | None


ResourceGuardLevel = Literal["L0", "L1", "L2", "L3", "L4"]


class SystemMetrics(ProtocolModel):
    ts: datetime
    game_fps: float | None = Field(description="null when no game is running (UI shows n/a)")
    game_frametime_p99_ms: float | None
    cpu_pct: float
    ram_used_mb: int
    ram_total_mb: int
    gpu: list[GpuMetrics] = Field(description="Empty on non-NVIDIA GPUs in v1 (UI shows n/a)")
    tokens_per_min: int = Field(ge=0)
    llm_queue_depth: int = Field(ge=0)
    goals_active: int = Field(ge=0)
    tasks_open: int = Field(ge=0)
    resource_guard_level: ResourceGuardLevel


class SafetyState(ProtocolModel):
    killed: bool
    armed: bool
    control_owner: ControlOwner
    last_kill_at: datetime | None
    last_kill_source: str | None
    policy_version: int = Field(ge=0)


class JobUpdateData(ProtocolModel):
    id: UUID
    kind: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float = Field(ge=0, le=1)
    error: str | None = None


WS_MESSAGE_TYPES: dict[str, type[ProtocolModel]] = {
    "chat.start": ChatStartData,
    "chat.delta": ChatDeltaData,
    "chat.final": ChatFinalData,
    "chat.cancelled": ChatCancelledData,
    "user.say": UserSayData,
    "system.notice": SystemNoticeData,
    "agent.state": AgentStateData,
    "task.update": TaskUpdateData,
    "floor.state": FloorStateData,
    "bb.update": BBUpdateData,
    "telemetry.frame": TelemetryFrameUI,
    "game.event": GameEvent,
    "session.state": SessionStateData,
    "session.ended": SessionEndedData,
    "recording.status": RecordingStatus,
    "system.metrics": SystemMetrics,
    "safety.state": SafetyState,
    "job.update": JobUpdateData,
}
"""`MsgFrame.type` to the model describing `MsgFrame.data`."""
