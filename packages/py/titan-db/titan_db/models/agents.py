"""ORM models for agent personas, teams, and agent definitions."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class AgentPersona(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_personas"

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str] = mapped_column(Text, nullable=False)
    personality: Mapped[dict] = mapped_column(JSONB, nullable=False)
    backstory: Mapped[str | None] = mapped_column(Text)
    speaking_style: Mapped[str | None] = mapped_column(Text)
    system_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[dict | None] = mapped_column(JSONB)
    portrait_path: Mapped[str | None] = mapped_column(Text)
    color_hex: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        server_default="#888888",
    )
    model_role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="agent",
    )
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="SET NULL"),
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )


class AgentTeam(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_teams"
    __table_args__ = (UniqueConstraint("game_id", "name", "version"),)

    game_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    template_slug: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )

    agents: Mapped[list[Agent]] = relationship(back_populates="team")


class Agent(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("team_id", "role"),
        CheckConstraint("can_act = false", name="p1_no_actions"),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_personas.id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_director: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    responsibilities: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    bb_read_sections: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{goals,plan,world_state,facts,risks}'::text[]"),
    )
    bb_write_sections: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{facts,hypotheses,risks,discoveries}'::text[]"),
    )
    event_subscriptions: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    tick_interval_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="10000",
    )
    can_commentate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    can_act: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="active",
    )
    stats: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    team: Mapped[AgentTeam] = relationship(back_populates="agents")
    persona: Mapped[AgentPersona] = relationship()
