"""
ODW.ai Desk — AI Configuration Model

Stores AI engine configuration for a deployment.
"""

from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from desk.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    AI Configuration entity.

    Stores AI engine settings including model endpoints, routing policies,
    and Vault integration for a deployment.
    """

    __tablename__ = "ai_configurations"

    deployment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        comment="One config per deployment",
    )
    local_model_endpoint: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Ollama/vLLM endpoint URL",
    )
    local_model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model identifier (e.g., llama-3.1-8b)",
    )
    frontier_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="openai, anthropic",
    )
    frontier_model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="e.g., gpt-4o, claude-3.5-sonnet",
    )
    frontier_api_key_encrypted: Mapped[bytes | None] = mapped_column(
        BYTEA,
        nullable=True,
        comment="Encrypted API key",
    )
    routing_policy: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Routing rules (complexity threshold, PII policy)",
    )
    system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Base system prompt for AI",
    )
    confidence_threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.7,
        comment="Global default confidence threshold",
    )
    vault_collection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="Default Vault collection for retrieval",
    )
    pii_shield_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Enable PII detection",
    )
    pii_frontier_allowed_with_redaction: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow frontier if PII redacted",
    )
    active_persona_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("brand_personas.id", ondelete="SET NULL"),
        nullable=True,
        comment="Currently active Brand Persona",
    )

    __table_args__ = (
        Index("idx_ai_configurations_deployment", "deployment_id", unique=True),
        Index(
            "idx_ai_configurations_active_persona",
            "active_persona_id",
            postgresql_where="active_persona_id IS NOT NULL",
        ),
    )

    def __repr__(self) -> str:
        return f"<AIConfiguration(id={self.id}, deployment_id={self.deployment_id})>"
