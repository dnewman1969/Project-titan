"""ORM models for research, knowledge, strategy, risk, controls, and memories."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class ResearchSource(Base, UuidPrimaryKeyMixin):
    __tablename__ = "research_sources"
    __table_args__ = (UniqueConstraint("game_id", "url"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    robots_allowed: Mapped[bool | None] = mapped_column(Boolean)
    license_note: Mapped[str | None] = mapped_column(Text)
    raw_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class KnowledgeEntry(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_entries"
    __table_args__ = (UniqueConstraint("game_id", "content_hash"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    structured: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_sources.id", ondelete="SET NULL"),
    )
    game_version: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
    )
    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chroma_id: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', title || ' ' || body)", persisted=True),
    )


class Strategy(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "strategies"

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
    )
    times_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    times_succeeded: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="candidate",
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id"),
    )
    game_version_range: Mapped[str | None] = mapped_column(Text)
    chroma_id: Mapped[str | None] = mapped_column(Text)


class RiskEntry(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "risk_entries"

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_conditions: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    likelihood: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mitigation: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    occurrences: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ControlBinding(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "control_bindings"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "game_profile_id",
            "action_id",
            "context",
            "device",
            postgresql_nulls_not_distinct=True,
        ),
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    game_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("game_profiles.id", ondelete="CASCADE"),
    )
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_label: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="default",
    )
    device: Mapped[str] = mapped_column(Text, nullable=False)
    binding: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action_class: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="1.0",
    )


class Memory(Base, UuidPrimaryKeyMixin):
    __tablename__ = "memories"

    game_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="SET NULL"),
    )
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.7",
    )
    t_session_ms: Mapped[int | None] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    access_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memories.id"),
    )
    chroma_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
