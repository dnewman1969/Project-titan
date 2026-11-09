"""ORM models for blackboard, events, messages, telemetry, and LLM calls."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from titan_db.models.base import Base, UuidPrimaryKeyMixin


class BlackboardEntry(Base, UuidPrimaryKeyMixin):
    __tablename__ = "blackboard_entries"
    __table_args__ = (UniqueConstraint("session_id", "section", "key", "version"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    op: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bb_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Event(Base, UuidPrimaryKeyMixin):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    salience: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.3",
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    t_mono_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    t_session_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    frame_seq: Mapped[int | None] = mapped_column(BigInteger)


class AgentMessage(Base, UuidPrimaryKeyMixin):
    __tablename__ = "agent_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stream_seq: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    recipients: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    t_session_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TelemetrySample(Base):
    __tablename__ = "telemetry_samples"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    t_session_ms: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    frame: Mapped[dict] = mapped_column(JSONB, nullable=False)


class LlmCall(Base, UuidPrimaryKeyMixin):
    __tablename__ = "llm_calls"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    agent_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_role: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    prompt_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
