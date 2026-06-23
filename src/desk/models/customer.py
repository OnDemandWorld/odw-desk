"""
ODW.ai Desk — Customer Model

Represents a customer with channel-specific identifiers.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from desk.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from desk.models.conversation import Conversation


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Customer entity.

    Stores customer information with channel-specific identifiers
    (e.g., phone number for WhatsApp, email for email channel).
    """

    __tablename__ = "customers"

    display_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Customer display name"
    )
    channel_identifiers: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Map of channel → identifier (e.g., {\"whatsapp\": \"+1234567890\"})",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Custom metadata (tags, notes)",
    )

    # Relationships
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_customers_channel_identifiers", "channel_identifiers", postgresql_using="gin"),
        Index("idx_customers_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, display_name={self.display_name})>"
