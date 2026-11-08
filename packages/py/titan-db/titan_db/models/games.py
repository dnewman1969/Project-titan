"""ORM models for games and detected installations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Game(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "games"

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_id: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_version: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    genres: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    capabilities: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    store_ids: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    research_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="none",
    )
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)

    profiles: Mapped[list[GameProfile]] = relationship(back_populates="game")


class GameProfile(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "game_profiles"
    __table_args__ = (UniqueConstraint("game_id", "install_path"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    store: Mapped[str] = mapped_column(Text, nullable=False)
    install_path: Mapped[str] = mapped_column(Text, nullable=False)
    executable_path: Mapped[str] = mapped_column(Text, nullable=False)
    launch_uri: Mapped[str | None] = mapped_column(Text)
    launch_args: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    game_version: Mapped[str | None] = mapped_column(Text)
    config_paths: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    save_paths: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    mod_paths: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    telemetry_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="unknown",
    )
    telemetry_details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    game: Mapped[Game] = relationship(back_populates="profiles")
