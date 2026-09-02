"""
ODW.ai Desk — Message Model

Represents a message in a conversation.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from desk.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from desk.models.brand_persona import BrandPersona
    from desk.models.conversation import Conversation


class Message(UUIDPrimaryKeyMixin, Base):
    """
    Message entity.

    Represents a single message in a conversation (customer, AI, or agent).
    Tracks PII detection, persona used, and policy triggers.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="Conversation reference",
    )
    sender_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="customer, ai, agent, system",
    )
    sender_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Agent ID or 'ai' or customer channel ID",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message text (may be encrypted for PII)",
    )
    content_redacted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Redacted version (if PII detected)",
    )
    media_urls: Mapped[list] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Array of media file URLs",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="AI metadata: model, confidence, routing decision",
    )
    pii_detected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether PII was detected",
    )
    pii_types: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Array of PII types found",
    )
    channel_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Channel-specific message ID (for dedup)",
    )
    persona_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("brand_personas.id", ondelete="SET NULL"),
        nullable=True,
        comment="Brand Persona used for this message (if AI-generated)",
    )
    persona_backend_used: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="prompt or lora_adapter — which persona backend generated this",
    )
    policy_triggers: Mapped[list] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Array of policy decisions: [{policy_id, action, matched_on, timestamp}]",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        comment="Message timestamp",
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the message was marked read (read receipt, V1.6 F-4); null = unread",
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    persona: Mapped["BrandPersona | None"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_messages_conversation_created", "conversation_id", "created_at"),
        Index(
            "idx_messages_sender_type",
            "sender_type",
            postgresql_where="sender_type = 'ai'",
        ),
        Index(
            "idx_messages_channel_message_id",
            "conversation_id",
            "channel_message_id",
            unique=True,
            postgresql_where="channel_message_id IS NOT NULL",
        ),
        Index(
            "idx_messages_persona_id",
            "persona_id",
            postgresql_where="persona_id IS NOT NULL",
        ),
        Index("idx_messages_policy_triggers", "policy_triggers", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, sender_type={self.sender_type}, conversation_id={self.conversation_id})>"
