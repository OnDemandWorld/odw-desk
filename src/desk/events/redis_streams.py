"""
ODW.ai Desk — Redis Streams Event Bus

Implementation of the EventBus interface using Redis Streams.
"""

import json
from typing import Any

from desk.events.bus import EventBus
from desk.utils.redis_client import RedisConnectionManager


class RedisStreamsEventBus(EventBus):
    """
    Redis Streams implementation of the event bus.

    Supports consumer groups, at-least-once delivery, and a dead-letter queue.
    """

    def __init__(self, redis_manager: RedisConnectionManager):
        self.redis_manager = redis_manager

    async def connect(self) -> None:
        """Initialize Redis connection."""
        await self.redis_manager.connect()

    async def disconnect(self) -> None:
        """Close Redis connection."""
        await self.redis_manager.disconnect()

    async def publish(self, stream: str, event: dict[str, Any]) -> str:
        """
        Publish an event to a Redis Stream.

        Args:
            stream: Stream name
            event: Event payload

        Returns:
            Message ID
        """
        event_json = json.dumps(event)
        async with self.redis_manager.get_client() as client:
            message_id = await client.xadd(stream, {"payload": event_json})
            return str(message_id)

    async def subscribe(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        """
        Read events from a Redis Stream consumer group.

        Args:
            stream: Stream name
            consumer_group: Consumer group name
            consumer_name: Consumer name
            count: Maximum number of messages to read
            block_ms: Blocking timeout in milliseconds

        Returns:
            List of events with `event_id` and `payload` fields
        """
        async with self.redis_manager.get_client() as client:
            # Create consumer group if it doesn't exist (idempotent)
            try:
                await client.xgroup_create(stream, consumer_group, id="0", mkstream=True)
            except Exception as e:
                # Group may already exist
                error_str = str(e)
                if "already exists" not in error_str:
                    raise

            # Read messages
            messages = await client.xreadgroup(
                consumer_group,
                consumer_name,
                {stream: ">"},
                count=count,
                block=block_ms,
            )

            events: list[dict[str, Any]] = []
            for stream_name, entries in messages:
                for message_id, fields in entries:
                    payload_str = fields.get("payload", "{}")
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError:
                        payload = {"raw_payload": payload_str}

                    events.append(
                        {
                            "event_id": str(message_id),
                            "stream": stream,
                            "consumer_group": consumer_group,
                            "payload": payload,
                        }
                    )
            return events

    async def acknowledge(self, stream: str, consumer_group: str, message_id: str) -> None:
        """
        Acknowledge a message in the consumer group.

        Args:
            stream: Stream name
            consumer_group: Consumer group name
            message_id: Message ID to acknowledge
        """
        async with self.redis_manager.get_client() as client:
            await client.xack(stream, consumer_group, message_id)

    async def dead_letter(self, stream: str, event: dict[str, Any], reason: str) -> None:
        """
        Move a failed event to the dead-letter stream.

        Args:
            stream: Original stream name
            event: Event payload
            reason: Failure reason
        """
        dlq_stream = f"{stream}:dlq"
        dlq_event = {
            "original_stream": stream,
            "reason": reason,
            "payload": event,
        }
        async with self.redis_manager.get_client() as client:
            await client.xadd(dlq_stream, {"payload": json.dumps(dlq_event)})
