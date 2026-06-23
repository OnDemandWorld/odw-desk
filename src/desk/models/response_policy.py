"""
ODW.ai Desk — Response Policy Model

Configurable response rules and guardrails.
"""

from uuid import UUID

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from desk.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResponsePolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Response Policy entity.

    Defines rules for handling sensitive topics (competitors, pricing, legal/medical).
    Supports pre-generation and post-generation hooks.
    """

    __tablename__ = "response_policies"

    deployment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="Deployment reference",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Policy name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="keyword, classifier, llm_intent",
    )
    trigger_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Trigger configuration",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="template, redirect, inject_context, append_disclaimer, block, escalate",
    )
    action_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Action-specific payload",
    )
    applies_to: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pre",
        comment="pre, post, both",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="Evaluation order (lower = higher priority)",
    )
    restricted_topics: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Array of restricted topic labels",
    )
    allow_general_knowledge_fallback: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether to allow LLM general knowledge when no Vault doc found",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this policy is currently active",
    )

    __table_args__ = (
        Index(
            "idx_response_policies_deployment_active",
            "deployment_id",
            "is_active",
            "priority",
            postgresql_where="is_active = true",
        ),
        Index("idx_response_policies_trigger_type", "trigger_type"),
        Index("idx_response_policies_applies_to", "applies_to"),
    )

    def __repr__(self) -> str:
        return f"<ResponsePolicy(id={self.id}, name={self.name}, action={self.action})>"
