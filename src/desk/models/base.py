"""
ODW.ai Desk — SQLAlchemy Base & Mixins

Provides declarative base and common mixins for all models.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class for all models."""

    pass


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamp columns.

    - created_at: Set automatically on insert, never updated
    - updated_at: Set automatically on insert, updated on every modification
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        comment="Last update timestamp",
    )


class UUIDPrimaryKeyMixin:
    """
    Mixin that adds a UUID primary key column.

    Uses PostgreSQL's native UUID type for efficient storage.
    Auto-generates UUIDs using gen_random_uuid() if not provided.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        comment="Unique identifier (UUID)",
    )
