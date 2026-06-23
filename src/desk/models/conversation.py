"""
ODW.ai Desk — Conversation Model

Represents a conversation thread with a customer.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from desk.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from desk.models.agent import Agent
    from desk.models.customer import Customer
    from desk.models.message import Message


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Conversation entity.

    Represents a conversation thread with a customer on a specific channel.
    Tracks state machine, SLA timers, and AI/human assignment.
    """

    __tablename__ = "conversations"

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        comment="Customer reference",
    )
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Channel type: whatsapp, webchat, email, telegram, discord, slack, signal",
    )
    channel_conversation_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Channel-specific conversation/thread ID",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="new",
        comment="State: new, active, pending, escalated, resolved, closed",
    )
    assigned_agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Human agent (if escalated)",
    )
    ai_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether AI auto-responds",
    )
    confidence_threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.7,
        comment="Minimum confidence for AI response",
    )
    sla_first_response_due: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="SLA deadline for first response",
    )
    sla_resolution_due: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="SLA deadline for resolution",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Channel-specific metadata",
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="conversations")
    assigned_agent: Mapped["Agent | None"] = relationship(back_populates="assigned_conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )

    __table_args__ = (
        Index(
            "idx_conversations_customer_status",
            "customer_id",
            "status",
            "updated_at",
        ),
        UniqueConstraint(
            "channel",
            "channel_conversation_id",
            name="uq_conversations_channel_conversation_id",
        ),
        Index(
            "idx_conversations_assigned_agent",
            "assigned_agent_id",
            postgresql_where="assigned_agent_id IS NOT NULL",
        ),
        Index("idx_conversations_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, channel={self.channel}, status={self.status})>"
