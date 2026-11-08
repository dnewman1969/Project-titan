"""ORM models for video projects, publishing, and analytics."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from titan_db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class VideoProject(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "video_projects"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="draft",
    )
    timeline_path: Mapped[str | None] = mapped_column(Text)
    timeline_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    render_profile: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    output_path: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    chapters: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    captions_path: Mapped[str | None] = mapped_column(Text)
    seo: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )


class VideoProjectSource(Base):
    __tablename__ = "video_project_sources"

    video_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Thumbnail(Base, UuidPrimaryKeyMixin):
    __tablename__ = "thumbnails"

    video_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    style: Mapped[str] = mapped_column(Text, nullable=False)
    source_marker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markers.id", ondelete="SET NULL"),
    )
    prompt: Mapped[str | None] = mapped_column(Text)
    generator: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    ctr: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PlatformAccount(Base, UuidPrimaryKeyMixin):
    __tablename__ = "platform_accounts"
    __table_args__ = (UniqueConstraint("platform", "remote_channel_id"),)

    platform: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    remote_channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    credential_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UploadJob(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "upload_jobs"
    __table_args__ = (
        CheckConstraint(
            "status NOT IN ('approved','uploading','processing','scheduled','published') "
            "OR approved_at IS NOT NULL",
            name="approval_required",
        ),
    )

    video_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_accounts.id"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="draft",
    )
    privacy: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="private",
    )
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_session_uri: Mapped[str | None] = mapped_column(Text)
    bytes_sent: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    bytes_total: Mapped[int | None] = mapped_column(BigInteger)
    remote_video_id: Mapped[str | None] = mapped_column(Text)
    remote_url: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    quota_units_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )


class AnalyticsSnapshot(Base, UuidPrimaryKeyMixin):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (UniqueConstraint("upload_job_id", "time_window", "captured_at"),)

    upload_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    remote_video_id: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_window: Mapped[str] = mapped_column(Text, nullable=False)
    views: Mapped[int | None] = mapped_column(BigInteger)
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    watch_time_minutes: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    avg_view_duration_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    avg_view_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    subscribers_gained: Mapped[int | None] = mapped_column(Integer)
    subscribers_lost: Mapped[int | None] = mapped_column(Integer)
    retention_curve: Mapped[list | None] = mapped_column(JSONB)
    raw: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
