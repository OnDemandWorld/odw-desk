"""
ODW.ai Desk — Agent Model

Represents a human support agent.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from desk.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from desk.models.conversation import Conversation


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Agent entity.

    Represents a human support agent who can take over conversations.
    """

    __tablename__ = "agents"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="ODW.ai Auth user reference",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Agent display name",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Agent email",
    )
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="agent",
        comment="admin, agent, read_only",
    )
    is_online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Current online status",
    )
    max_concurrent_conversations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        comment="Capacity limit",
    )

    # Relationships
    assigned_conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="assigned_agent"
    )

    __table_args__ = (
        Index("idx_agents_user_id", "user_id"),
        Index("idx_agents_online", "is_online", postgresql_where="is_online = true"),
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, display_name={self.display_name}, role={self.role})>"
