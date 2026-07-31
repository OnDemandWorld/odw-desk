"""
ODW.ai Desk — SLA Service

Evaluates conversations against the SLA policy and escalates breaches.

The evaluation maps onto the ACTUAL conversation schema:
- ``Conversation.created_at`` anchors the SLA windows.
- ``Conversation.sla_first_response_due`` / ``sla_resolution_due`` are honoured
  as explicit deadlines when present; otherwise deadlines are derived from the
  policy thresholds (``created_at + threshold``).
- A "first response" is the earliest message authored by ``ai`` or ``agent``
  (there is no dedicated timestamp column on the conversation).
- ``ConversationStatus`` provides the ``escalated`` target state.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from desk.config import get_settings
from desk.conversations.manager import ConversationManager
from desk.conversations.state_machine import ConversationStatus
from desk.events.bus import EventBus
from desk.models.conversation import Conversation
from desk.schemas.events import SLABreachEvent
from desk.sla.policy import SLAPolicy

logger = structlog.get_logger()


class SLAStatus(StrEnum):
    """Result of evaluating a conversation against the SLA policy."""

    OK = "ok"
    BREACHED_FIRST_RESPONSE = "breached_first_response"
    BREACHED_RESOLUTION = "breached_resolution"


# Conversations in these states are still subject to SLA enforcement.
ACTIVE_STATUSES: tuple[ConversationStatus, ...] = (
    ConversationStatus.NEW,
    ConversationStatus.ACTIVE,
    ConversationStatus.PENDING,
)

# Sender types that count as an outbound "first response" to the customer.
RESPONSE_SENDER_TYPES: tuple[str, ...] = ("ai", "agent")


class SLAService:
    """
    SLA Service.

    Responsibilities:
    - Evaluate a conversation against the policy (``evaluate``).
    - Escalate a conversation via the existing conversation manager/state
      machine and record a best-effort breach event (``escalate``).
    """

    def __init__(
        self,
        db: AsyncSession,
        policy: SLAPolicy | None = None,
        event_bus: EventBus | None = None,
    ):
        self.db = db
        self.policy = policy or SLAPolicy.from_settings(get_settings())
        self.manager = ConversationManager(db)
        self.event_bus = event_bus

    def evaluate(self, conversation: Conversation, now: datetime | None = None) -> SLAStatus:
        """
        Evaluate a conversation against the SLA policy.

        Args:
            conversation: Conversation entity (``messages`` may be loaded).
            now: Reference time (defaults to current UTC time).

        Returns:
            ``SLAStatus.OK`` when within SLA, otherwise the breached milestone.
            First-response breach takes precedence over resolution breach.
        """
        now = self._aware(now) or datetime.now(tz=UTC)

        try:
            status = ConversationStatus(conversation.status)
        except ValueError:
            status = None
        # Only active-life conversations are enforced; resolved/closed/escalated
        # conversations are no longer subject to SLA escalation.
        if status not in ACTIVE_STATUSES:
            return SLAStatus.OK

        created_at = self._aware(conversation.created_at) or now

        # First-response milestone: breached only if no response has been sent.
        if self._first_response_at(conversation) is None:
            first_response_due = self._aware(conversation.sla_first_response_due) or (
                created_at + timedelta(minutes=self.policy.first_response_minutes)
            )
            if now > first_response_due:
                return SLAStatus.BREACHED_FIRST_RESPONSE

        # Resolution milestone.
        resolution_due = self._aware(conversation.sla_resolution_due) or (
            created_at + timedelta(minutes=self.policy.resolution_minutes)
        )
        if now > resolution_due:
            return SLAStatus.BREACHED_RESOLUTION

        return SLAStatus.OK

    async def escalate(self, conversation_id, reason: str | None = None) -> bool:
        """
        Escalate a conversation to the ``escalated`` state.

        Uses the existing conversation manager (state-machine validated) and
        records a best-effort SLA breach event. Returns True when the
        conversation was escalated, False when skipped (not found, already
        escalated, or invalid transition).
        """
        conversation = await self.manager.get_conversation_by_id(conversation_id)
        if conversation is None:
            logger.warning(
                "SLA escalation skipped: conversation not found",
                conversation_id=str(conversation_id),
            )
            return False

        if conversation.status == ConversationStatus.ESCALATED:
            return False

        # Evaluate before the state change so the breach type is still derivable.
        breach = self.evaluate(conversation)

        try:
            await self.manager.update_status(
                conversation, ConversationStatus.ESCALATED, reason=reason
            )
        except ValueError as exc:
            logger.warning(
                "SLA escalation skipped: invalid state transition",
                conversation_id=str(conversation_id),
                status=conversation.status,
                error=str(exc),
            )
            return False

        logger.info(
            "SLA escalation applied",
            conversation_id=str(conversation_id),
            breach=breach.value,
            reason=reason,
        )
        await self._publish_breach(conversation, breach)
        return True

    async def _publish_breach(self, conversation: Conversation, breach: SLAStatus) -> None:
        """Publish an SLA breach event best-effort (never raises)."""
        if self.event_bus is None:
            return
        sla_type = (
            "resolution"
            if breach is SLAStatus.BREACHED_RESOLUTION
            else "first_response"
        )
        due_at = (
            self._aware(conversation.sla_resolution_due)
            if breach is SLAStatus.BREACHED_RESOLUTION
            else self._aware(conversation.sla_first_response_due)
        ) or datetime.now(tz=UTC)
        try:
            event = SLABreachEvent(
                conversation_id=str(conversation.id),
                sla_type=sla_type,
                due_at=due_at,
            )
            await self.event_bus.publish("sla.breach", event.model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SLA breach event publish failed (best-effort)",
                conversation_id=str(conversation.id),
                error=str(exc),
            )

    @staticmethod
    def _first_response_at(conversation: Conversation) -> datetime | None:
        """Earliest ai/agent message timestamp, or None if no response yet."""
        messages = getattr(conversation, "messages", None) or []
        times = [
            SLAService._aware(message.created_at)
            for message in messages
            if getattr(message, "sender_type", None) in RESPONSE_SENDER_TYPES
            and getattr(message, "created_at", None) is not None
        ]
        times = [t for t in times if t is not None]
        return min(times) if times else None

    @staticmethod
    def _aware(dt: datetime | None) -> datetime | None:
        """Normalise a datetime to timezone-aware UTC (None passes through)."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
