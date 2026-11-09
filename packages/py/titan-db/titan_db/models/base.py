"""SQLAlchemy declarative base and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Titan ORM models (DDL in Section 4.2)."""


class UuidPrimaryKeyMixin:
    """Primary key column ``id`` as PostgreSQL ``uuid``."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class TimestampMixin:
    """``created_at`` / ``updated_at`` with server default ``now()``."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
