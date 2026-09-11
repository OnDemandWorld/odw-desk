"""
ODW.ai Desk — Conversation Manager

Manages conversation state, persists messages, and enforces SLA timers.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.conversations.state_machine import ConversationStateMachine, ConversationStatus
from desk.models.agent import Agent
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message


class ConversationManager:
    """
    Conversation Manager.

    Responsibilities:
    - Create or retrieve conversations by customer + channel
    - Persist customer and AI messages
    - Manage conversation state machine
    - Track SLA timers (first response, resolution)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_conversation_by_id(self, conversation_id: UUID | str) -> Conversation | None:
        """
        Get a conversation by its UUID.

        Args:
            conversation_id: Conversation UUID (string or UUID object)

        Returns:
            Conversation entity or None if not found
        """
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_conversation(
        self,
        customer: Customer,
        channel: str,
        channel_conversation_id: str,
    ) -> Conversation:
        """
        Get an existing active conversation or create a new one.

        Args:
            customer: Customer entity
            channel: Channel type
            channel_conversation_id: Channel-specific conversation ID

        Returns:
            Existing or new Conversation
        """
        # Look up by the exact (channel, channel_conversation_id) thread across
        # ALL statuses. uq_conversations_channel_conversation_id guarantees at
        # most one row per thread, so a resolved/closed conversation can never
        # be re-created — creating one raised IntegrityError and lost the
        # customer's message (webhook 500).
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.customer_id == customer.id)
            .where(Conversation.channel == channel)
            .where(Conversation.channel_conversation_id == channel_conversation_id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        conversation = result.scalar_one_or_none()

        if conversation is not None:
            # Customer came back: reopen finished conversations. RESOLVED →
            # ACTIVE is a state-machine transition; CLOSED allows none, but the
            # unique constraint forbids a replacement row, so the thread is
            # force-reopened to keep customer messages flowing.
            if conversation.status in (
                ConversationStatus.RESOLVED,
                ConversationStatus.CLOSED,
            ):
                conversation.status = ConversationStatus.ACTIVE
                await self.db.flush()
            return conversation

        conversation = Conversation(
            customer_id=customer.id,
            channel=channel,
            channel_conversation_id=channel_conversation_id,
            status=ConversationStatus.NEW,
            ai_enabled=True,
            confidence_threshold=0.7,
        )
        self.db.add(conversation)
        await self.db.flush()

        return conversation

    async def add_message(
        self,
        conversation: Conversation,
        sender_type: str,
        sender_id: str | None,
        content: str,
        channel_message_id: str | None = None,
        metadata: dict | None = None,
    ) -> Message:
        """
        Add a message to a conversation.

        Args:
            conversation: Conversation entity
            sender_type: customer, ai, agent, system
            sender_id: Agent ID, "ai", or customer channel ID
            content: Message text
            channel_message_id: Channel-specific message ID
            metadata: Additional metadata

        Returns:
            Created Message entity
        """
        message = Message(
            conversation_id=conversation.id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            channel_message_id=channel_message_id,
            metadata_=metadata or {},
            created_at=datetime.now(tz=UTC),
        )
        self.db.add(message)

        # Update conversation state when customer sends a message
        if sender_type == "customer":
            if conversation.status == ConversationStatus.PENDING:
                conversation.status = ConversationStatus.ACTIVE
            elif conversation.status == ConversationStatus.NEW:
                conversation.status = ConversationStatus.ACTIVE

        # Update first response SLA if this is the first message
        await self._ensure_first_response_sla(conversation)

        await self.db.flush()
        return message

    async def update_status(
        self,
        conversation: Conversation,
        new_status: str,
        reason: str | None = None,
    ) -> None:
        """
        Update conversation status with state machine validation.

        Args:
            conversation: Conversation entity
            new_status: New status value
            reason: Optional reason for state change
        """
        ConversationStateMachine.transition(conversation.status, new_status)
        conversation.status = new_status

        if reason:
            # Update metadata with reason
            metadata = conversation.metadata_ or {}
            metadata["last_status_change_reason"] = reason
            conversation.metadata_ = metadata

        if new_status == ConversationStatus.RESOLVED:
            await self._mark_resolution(conversation)

        await self.db.flush()

    async def assign_agent(self, conversation: Conversation, agent: Agent) -> None:
        """Assign a human agent to a conversation."""
        conversation.assigned_agent_id = agent.id
        conversation.status = ConversationStatus.ESCALATED
        await self.db.flush()

    async def _ensure_first_response_sla(self, conversation: Conversation) -> None:
        """Set first-response SLA if not already set."""
        if conversation.sla_first_response_due is None:
            # Use default 10 minutes from config in real implementation
            conversation.sla_first_response_due = datetime.now(tz=UTC) + timedelta(minutes=10)

    async def _mark_resolution(self, conversation: Conversation) -> None:
        """Mark conversation as resolved and clear agent assignment."""
        conversation.assigned_agent_id = None
        conversation.sla_resolution_due = None
