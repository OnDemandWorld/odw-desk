"""
ODW.ai Desk — Message Router

Routes inbound messages to the appropriate processing pipeline.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.conversations.manager import ConversationManager
from desk.events.redis_streams import RedisStreamsEventBus
from desk.models.message import Message
from desk.router.customer_resolver import CustomerResolver
from desk.schemas.channels import InboundMessage


class MessageRouter:
    """
    Message Router.

    Receives canonical inbound messages, resolves or creates customers,
    loads conversation context, and dispatches to the AI or human pipeline.
    """

    def __init__(
        self,
        db: AsyncSession,
        event_bus: RedisStreamsEventBus,
    ):
        self.db = db
        self.event_bus = event_bus
        self.customer_resolver = CustomerResolver(db)
        self.conversation_manager = ConversationManager(db)

    async def route(self, message: InboundMessage) -> dict:
        """
        Route an inbound message to the appropriate pipeline.

        Args:
            message: Canonical inbound message

        Returns:
            Routing result with customer_id and conversation_id
        """
        # Resolve or create customer
        customer = await self.customer_resolver.resolve_or_create(
            channel=message.channel,
            identifier=message.sender_identifier,
            display_name=message.sender_name,
        )

        # Get or create conversation
        conversation = await self.conversation_manager.get_or_create_conversation(
            customer=customer,
            channel=message.channel,
            channel_conversation_id=message.conversation_id,
        )

        # Idempotency: channel providers redeliver webhooks on any non-2xx or
        # timeout (Meta retries for up to 7 days). The first delivery usually
        # committed, so replaying the insert hit the
        # UNIQUE(conversation_id, channel_message_id) index, turned into a 500,
        # and invited the next redelivery — an infinite loop. Treat a known
        # channel_message_id as already-routed and return immediately.
        if message.message_id:
            dup = await self.db.execute(
                select(Message.id).where(
                    Message.conversation_id == conversation.id,
                    Message.channel_message_id == message.message_id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                return {
                    "customer_id": str(customer.id),
                    "conversation_id": str(conversation.id),
                    "status": "duplicate",
                }

        # Persist inbound message. Rich-media metadata (V1.6 F-4, DC2) carried in
        # ``message.metadata["media"]`` (image/file url/mime/name/size) is stored
        # on the message record so it survives beyond the V1.4 in-memory handling.
        persisted_metadata: dict = {
            "channel": message.channel,
            "timestamp": message.timestamp.isoformat() if message.timestamp else None,
            "media_urls": message.media_urls,
        }
        media = message.metadata.get("media")
        if media:
            persisted_metadata["media"] = media

        await self.conversation_manager.add_message(
            conversation=conversation,
            sender_type="customer",
            sender_id=message.sender_identifier,
            content=message.content,
            channel_message_id=message.message_id,
            metadata=persisted_metadata,
        )

        # Publish routing event to event bus for AI processing
        await self.event_bus.publish(
            "conversation.routed",
            {
                "customer_id": str(customer.id),
                "conversation_id": str(conversation.id),
                "message_id": message.message_id,
                "channel": message.channel,
                "sender_identifier": message.sender_identifier,
                "content": message.content,
                "routed_at": datetime.now(tz=UTC).isoformat(),
            },
        )

        return {
            "customer_id": str(customer.id),
            "conversation_id": str(conversation.id),
            "status": "routed",
        }
