"""
ODW.ai Desk — Message Processor Worker

Listens to routed conversation events, invokes the AI engine,
and dispatches outbound responses.
"""

import asyncio
import json

import structlog

from desk.ai.engine import AIEngine
from desk.channels.outbound import OutboundDispatcher
from desk.events.redis_streams import RedisStreamsEventBus
from desk.utils.redis_client import get_redis_manager

logger = structlog.get_logger()


class MessageProcessor:
    """
    Background worker that processes routed messages.

    Subscribes to the `conversation.routed` stream and:
    1. Calls the AI engine to generate a response
    2. Persists the response as an AI message
    3. Dispatches the response via the outbound dispatcher
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

    async def _process_message(self, message: dict) -> None:
        """Process a single routed message."""
        try:
            event_id = message["event_id"]
            payload = message.get("payload", {})

            conversation_id = payload.get("conversation_id")
            content = payload.get("content", "")
            channel = payload.get("channel", "")
            sender_identifier = payload.get("sender_identifier", "")

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

            # Create outbound message
            outbound = await self.ai_engine.create_outbound_message(
                conversation_id=conversation_id,
                channel=channel,
                recipient=sender_identifier,
                content=response,
            )

            # Dispatch response
            result = await self.outbound_dispatcher.dispatch(outbound)

            # Acknowledge event
            await self.event_bus.acknowledge(
                "conversation.routed",
                "ai-processors",
                event_id,
            )

            logger.info(
                "Message processed and dispatched",
                conversation_id=conversation_id,
                result=result,
            )

        except Exception as e:
            logger.error("Failed to process message", error=str(e))
            # In production, move to DLQ after max retries


async def run_processor() -> None:
    """Run the message processor."""
    from desk.channels.manager import ChannelAdapterManager
    from desk.channels.whatsapp_business import get_adapter as get_whatsapp_adapter
    from desk.channels.mock import MockChannelAdapter
    from desk.channels.base import AdapterConfig

    redis_manager = get_redis_manager()
    event_bus = RedisStreamsEventBus(redis_manager)
    await event_bus.connect()

    channel_manager = ChannelAdapterManager(event_bus, redis_manager)

    # Register adapters
    channel_manager.register(MockChannelAdapter(AdapterConfig(adapter_id="mock", adapter_name="Mock", channel_type="mock")))
    whatsapp_adapter = get_whatsapp_adapter()
    if whatsapp_adapter:
        channel_manager.register(whatsapp_adapter)

    outbound_dispatcher = OutboundDispatcher(channel_manager)
    ai_engine = AIEngine()

    processor = MessageProcessor(event_bus, outbound_dispatcher, ai_engine)
    await processor.run()


if __name__ == "__main__":
    asyncio.run(run_processor())
