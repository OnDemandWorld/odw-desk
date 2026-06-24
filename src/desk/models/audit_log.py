"""
ODW.ai Desk — Audit Log Model

Tamper-evident audit log for compliance.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from desk.models.base import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """
    Audit Log entity.

    Tamper-evident audit log with hash chaining for compliance.
    Records all AI decisions, data access, and administrative actions.
    """

    __tablename__ = "audit_logs"

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="Event timestamp",
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="ai_decision, data_access, data_deletion, config_change, login, policy_decision, persona_applied",
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="ai, agent, admin, system",
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="Agent or Admin ID (nullable for AI/system)",
    )
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Resource accessed (e.g., conversation, customer)",
    )
    resource_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="Resource ID",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action taken (e.g., read, delete, respond)",
    )
    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Event details (e.g., model used, confidence score)",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Actor's IP address",
    )
    previous_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Hash of previous log entry (for tamper detection)",
    )
    hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Hash of this log entry",
    )

    __table_args__ = (
        Index("idx_audit_logs_timestamp", "timestamp"),
        Index("idx_audit_logs_event_type", "event_type"),
        Index("idx_audit_logs_resource", "resource_type", "resource_id"),
        Index("idx_audit_logs_actor", "actor_type", "actor_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, event_type={self.event_type}, action={self.action})>"
