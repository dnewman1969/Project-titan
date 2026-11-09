"""SQLAlchemy ORM models mirroring Section 4.2 DDL."""

from __future__ import annotations

from titan_db.models.agents import Agent, AgentPersona, AgentTeam
from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from titan_db.models.games import Game, GameProfile
from titan_db.models.knowledge import (
    ControlBinding,
    KnowledgeEntry,
    Memory,
    ResearchSource,
    RiskEntry,
    Strategy,
)
from titan_db.models.publishing import (
    AnalyticsSnapshot,
    PlatformAccount,
    Thumbnail,
    UploadJob,
    VideoProject,
    VideoProjectSource,
)
from titan_db.models.realtime import (
    AgentMessage,
    BlackboardEntry,
    Event,
    LlmCall,
    TelemetrySample,
)
from titan_db.models.recording import Marker, Recording, RecordingTrack
from titan_db.models.sessions import AgentInstance, Mission, Session, Task
from titan_db.models.settings import Setting

metadata = Base.metadata

__all__ = [
    "Agent",
    "AgentInstance",
    "AgentMessage",
    "AgentPersona",
    "AgentTeam",
    "AnalyticsSnapshot",
    "Base",
    "BlackboardEntry",
    "ControlBinding",
    "Event",
    "Game",
    "GameProfile",
    "KnowledgeEntry",
    "LlmCall",
    "Marker",
    "Memory",
    "Mission",
    "PlatformAccount",
    "Recording",
    "RecordingTrack",
    "ResearchSource",
    "RiskEntry",
    "Session",
    "Setting",
    "Strategy",
    "Task",
    "TelemetrySample",
    "Thumbnail",
    "TimestampMixin",
    "UploadJob",
    "UuidPrimaryKeyMixin",
    "VideoProject",
    "VideoProjectSource",
    "metadata",
]
