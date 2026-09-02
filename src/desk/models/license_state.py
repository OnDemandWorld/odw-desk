"""
ODW.ai Desk — License State Model

Tracks license validation and feature gates.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from desk.models.base import Base, UUIDPrimaryKeyMixin


class LicenseState(UUIDPrimaryKeyMixin, Base):
    """
    License State entity.

    Tracks license validation status and enabled features.
    """

    __tablename__ = "license_state"

    license_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="License key (encrypted at rest)",
    )
    tier: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="free, paid",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="active, expired, grace_period, invalid",
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="License expiry date",
    )
    grace_period_ends: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Grace period expiry",
    )
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Enabled features map",
    )
    last_validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Last successful validation",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        comment="Creation timestamp",
    )

    def __repr__(self) -> str:
        return f"<LicenseState(id={self.id}, tier={self.tier}, status={self.status})>"
