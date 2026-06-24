"""
ODW.ai Desk — Conversation State Machine

Defines valid conversation state transitions.
"""

from enum import StrEnum


class ConversationStatus(StrEnum):
    """Conversation status values."""

    NEW = "new"
    ACTIVE = "active"
    PENDING = "pending"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ConversationStateMachine:
    """
    Finite state machine for conversation lifecycle.

    Valid transitions:
    - new → active (first AI response or agent assignment)
    - active → pending (awaiting customer reply, 24h timeout)
    - active → escalated (AI confidence below threshold or explicit escalation)
    - escalated → active (agent takes over or hands back)
    - active → resolved (agent or AI confirms resolution)
    - resolved → closed (retention period expires or manual close)
    - resolved → active (customer sends new message)
    - pending → active (customer replies within window)
    - pending → closed (24h window expires without reply)
    - new → closed (admin cleanup)
    """

    VALID_TRANSITIONS: dict[ConversationStatus, set[ConversationStatus]] = {
        ConversationStatus.NEW: {
            ConversationStatus.ACTIVE,
            ConversationStatus.RESOLVED,
            ConversationStatus.CLOSED,
        },
        ConversationStatus.ACTIVE: {
            ConversationStatus.PENDING,
            ConversationStatus.ESCALATED,
            ConversationStatus.RESOLVED,
        },
        ConversationStatus.PENDING: {
            ConversationStatus.ACTIVE,
            ConversationStatus.CLOSED,
        },
        ConversationStatus.ESCALATED: {
            ConversationStatus.ACTIVE,
            ConversationStatus.RESOLVED,
        },
        ConversationStatus.RESOLVED: {
            ConversationStatus.ACTIVE,
            ConversationStatus.CLOSED,
        },
        ConversationStatus.CLOSED: set(),
    }

    @classmethod
    def can_transition(
        cls, current: ConversationStatus | str, new: ConversationStatus | str
    ) -> bool:
        """Check if a state transition is valid."""
        current_status = cls._to_status(current)
        new_status = cls._to_status(new)
        return new_status in cls.VALID_TRANSITIONS.get(current_status, set())

    @classmethod
    def transition(cls, current: ConversationStatus | str, new: ConversationStatus | str) -> None:
        """
        Validate a state transition.

        Args:
            current: Current state
            new: Desired new state

        Raises:
            ValueError: If transition is invalid
        """
        if not cls.can_transition(current, new):
            raise ValueError(f"Invalid transition: {current} → {new}")

    @classmethod
    def _to_status(cls, value: "ConversationStatus | str") -> ConversationStatus:
        """Convert string to ConversationStatus enum."""
        if isinstance(value, ConversationStatus):
            return value
        return ConversationStatus(value)
