"""ORM models for sessions, missions, agent instances, and tasks."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Session(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sessions"

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id"),
        nullable=False,
    )
    game_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("game_profiles.id", ondelete="SET NULL"),
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_teams.id", ondelete="SET NULL"),
    )
    title: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="observe",
    )
    state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="created",
    )
    replay_of_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
    )
    clock_origin_mono_ns: Mapped[int | None] = mapped_column(BigInteger)
    clock_origin_wall: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_dir: Mapped[str] = mapped_column(Text, nullable=False)
    game_version: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    outcome: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSONB)

    missions: Mapped[list[Mission]] = relationship(back_populates="session")
    tasks: Mapped[list[Task]] = relationship(back_populates="session")
    agent_instances: Mapped[list[AgentInstance]] = relationship(back_populates="session")


class Mission(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "missions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id"),
        nullable=False,
    )
    parent_mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    failure_criteria: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="planned",
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="5",
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)

    session: Mapped[Session] = relationship(back_populates="missions")


class AgentInstance(Base, UuidPrimaryKeyMixin):
    __tablename__ = "agent_instances"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    spawned_by: Mapped[str] = mapped_column(Text, nullable=False)
    spawned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    termination_reason: Mapped[str | None] = mapped_column(Text)
    model_resolved: Mapped[str | None] = mapped_column(Text)
    lg_thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    tokens_out: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    messages_sent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[Session] = relationship(back_populates="agent_instances")


class Task(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tasks"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="SET NULL"),
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[dict] = mapped_column(
        "input",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    output: Mapped[dict | None] = mapped_column(JSONB)
    assignee_role: Mapped[str | None] = mapped_column(Text)
    assignee_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
    )
    state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="proposed",
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="5",
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
    )
    max_attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="2",
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[dict | None] = mapped_column(JSONB)

    session: Mapped[Session] = relationship(back_populates="tasks")
