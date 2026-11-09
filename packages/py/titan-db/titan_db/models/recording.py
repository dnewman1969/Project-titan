"""ORM models for session recordings, tracks, and markers."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Recording(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "recordings"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    preset: Mapped[dict] = mapped_column(JSONB, nullable=False)
    start_mono_ns: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    root_dir: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_path: Mapped[str | None] = mapped_column(Text)
    total_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    error: Mapped[str | None] = mapped_column(Text)


class RecordingTrack(Base, UuidPrimaryKeyMixin):
    __tablename__ = "recording_tracks"
    __table_args__ = (UniqueConstraint("recording_id", "kind", "track_no"),)

    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    track_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    container: Mapped[str | None] = mapped_column(Text)
    codec: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(SmallInteger)
    start_offset_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    dropped_frames: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Marker(Base, UuidPrimaryKeyMixin):
    __tablename__ = "markers"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
    )
    t_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
    )
    label: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
