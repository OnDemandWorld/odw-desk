"""
ODW.ai Desk — Message Processor Worker

Listens to routed conversation events, invokes the AI engine,
persists the generated AI message, and dispatches outbound responses.
"""

import asyncio
from typing import Any

import structlog

from desk.ai.engine import AIEngine
from desk.channels.outbound import OutboundDispatcher
from desk.conversations.manager import ConversationManager
from desk.db import AsyncSessionLocal
from desk.events.redis_streams import RedisStreamsEventBus
from desk.schemas.channels import OutboundMessage
from desk.utils.redis_client import get_redis_manager

logger = structlog.get_logger()


class MessageProcessor:
    """
    Background worker that processes routed messages.

    Subscribes to the `conversation.routed` stream and:
    1. Calls the AI engine to generate a response
    2. Persists the response as an AI message in PostgreSQL
    3. Dispatches the response via the outbound dispatcher
    4. Acknowledges the event on success
    """

    def __init__(
        self,
        event_bus: RedisStreamsEventBus,
        outbound_dispatcher: OutboundDispatcher,
        ai_engine: AIEngine,
    ):
        self.event_bus = event_bus
        self.outbound_dispatcher = outbound_dispatcher
        self.ai_engine = ai_engine

    async def run(self) -> None:
        """Run the message processor loop."""
        logger.info("Starting message processor worker")

        while True:
            try:
                messages = await self.event_bus.subscribe(
                    "conversation.routed",
                    consumer_group="ai-processors",
                    consumer_name="processor-1",
                    count=10,
                    block_ms=5000,
                )

                for message in messages:
                    await self._process_message(message)

            except asyncio.CancelledError:
                logger.info("Message processor cancelled")
                break
            except Exception as e:
                logger.error("Error in message processor loop", error=str(e))
                await asyncio.sleep(1)

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Process a single routed message."""
        event_id = message.get("event_id")
        payload = message.get("payload", {})

        conversation_id = payload.get("conversation_id")
        content = payload.get("content", "")
        channel = payload.get("channel", "")
        sender_identifier = payload.get("sender_identifier", "")

        try:
            logger.info(
                "Processing message",
                conversation_id=conversation_id,
                channel=channel,
            )

            # Generate response with AI engine
            response = await self.ai_engine.process(
                conversation_id=conversation_id,
                content=content,
                channel=channel,
                recipient=sender_identifier,
            )

            # Persist the AI response and dispatch it
            outbound = await self._persist_and_build_outbound(
                conversation_id=conversation_id,
                channel=channel,
                recipient=sender_identifier,
                content=response,
            )

            if outbound is not None:
                await self.outbound_dispatcher.dispatch(outbound)

            # Acknowledge event
            if event_id:
                await self.event_bus.acknowledge(
                    "conversation.routed",
                    "ai-processors",
                    event_id,
                )

            logger.info(
                "Message processed and dispatched",
                conversation_id=conversation_id,
            )

        except Exception as e:
            logger.error("Failed to process message", error=str(e), conversation_id=conversation_id)
            # In production, move to DLQ after max retries
            if event_id:
                await self.event_bus.acknowledge(
                    "conversation.routed",
                    "ai-processors",
                    event_id,
                )

    async def _persist_and_build_outbound(
        self,
        conversation_id: str,
        channel: str,
        recipient: str,
        content: str,
    ) -> OutboundMessage | None:
        """
        Persist the AI response in the database and build an OutboundMessage.

        Returns the OutboundMessage, or None if the conversation no longer exists.
        """
        async with AsyncSessionLocal() as session:
            try:
                conversation_manager = ConversationManager(session)
                conversation = await conversation_manager.get_conversation_by_id(
                    conversation_id=conversation_id,
                )
                if conversation is None:
                    logger.warning(
                        "Conversation not found for AI response",
                        conversation_id=conversation_id,
                    )
                    return None

                await conversation_manager.add_message(
                    conversation=conversation,
                    sender_type="ai",
                    sender_id="ai",
                    content=content,
                    metadata={
                        "model": "stub",
                        "confidence": 1.0,
                        "routing": "local",
                    },
                )

                outbound = await self.ai_engine.create_outbound_message(
                    conversation_id=conversation_id,
                    channel=channel,
                    recipient=recipient,
                    content=content,
                )

                await session.commit()
                return outbound
            except Exception:
                await session.rollback()
                raise


async def run_processor() -> None:
    """Run the message processor."""
    from desk.channels.base import AdapterConfig
    from desk.channels.manager import ChannelAdapterManager
    from desk.channels.mock import MockChannelAdapter
    from desk.channels.whatsapp_business import get_adapter as get_whatsapp_adapter

    redis_manager = get_redis_manager()
    event_bus = RedisStreamsEventBus(redis_manager)
    await event_bus.connect()

    channel_manager = ChannelAdapterManager(event_bus, redis_manager)

    # Register adapters
    channel_manager.register(
        MockChannelAdapter(
            AdapterConfig(
                adapter_id="mock",
                adapter_name="Mock",
                channel_type="mock",
                enabled=True,
            )
        )
    )
    whatsapp_adapter = get_whatsapp_adapter()
    if whatsapp_adapter:
        channel_manager.register(whatsapp_adapter)

    outbound_dispatcher = OutboundDispatcher(channel_manager)
    ai_engine = AIEngine()

    processor = MessageProcessor(event_bus, outbound_dispatcher, ai_engine)
    await processor.run()
