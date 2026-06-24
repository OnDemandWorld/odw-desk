"""
ODW.ai Desk — Brand Persona Model

Configurable brand voice for AI responses.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from desk.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from desk.models.message import Message


class BrandPersona(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Brand Persona entity.

    Configures how the AI "sounds" — tone, vocabulary, formality, etc.
    Can be prompt-based or use a fine-tuned LoRA adapter.
    """

    __tablename__ = "brand_personas"

    deployment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="Deployment reference",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Persona name",
    )
    tone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tone descriptor (warm, formal, playful, professional)",
    )
    formality_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="neutral",
        comment="casual, neutral, formal",
    )
    vocabulary_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Custom vocabulary guidance",
    )
    dos: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Array of 'do' guidelines",
    )
    donts: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Array of 'don't' guidelines",
    )
    emoji_policy: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="moderate",
        comment="none, minimal, moderate, liberal",
    )
    signature_phrases: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Array of signature phrases",
    )
    few_shot_examples: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Array of example conversations for few-shot learning",
    )
    channel_overrides: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Per-channel persona overrides",
    )
    persona_backend: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="prompt",
        comment="prompt or lora_adapter",
    )
    adapter_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="LoRA/QLoRA adapter URI (when persona_backend = lora_adapter)",
    )
    adapter_base_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Expected base model for adapter",
    )
    adapter_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Adapter version identifier",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Persona config version",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this persona is currently active",
    )

    # Relationships
    messages: Mapped[list["Message"]] = relationship(back_populates="persona")

    __table_args__ = (
        Index(
            "idx_brand_personas_deployment_active",
            "deployment_id",
            "is_active",
            postgresql_where="is_active = true",
        ),
        Index("idx_brand_personas_name", "name"),
        Index("idx_brand_personas_backend", "persona_backend"),
    )

    def __repr__(self) -> str:
        return f"<BrandPersona(id={self.id}, name={self.name}, backend={self.persona_backend})>"
