"""
ODW.ai Desk — Redis Streams Event Bus

Implementation of the EventBus interface using Redis Streams.
"""

import json
from typing import Any

from redis import exceptions as redis_exceptions

from desk.events.bus import EventBus
from desk.utils.redis_client import RedisConnectionManager

# Audit #45: bounded stream retention — without MAXLEN, conversation.routed
# (full message content per entry) and the DLQs grow until Redis OOMs and the
# whole pipeline stalls. Approximate trimming keeps XADD cheap.
STREAM_MAXLEN = 100_000
DLQ_MAXLEN = 10_000


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
            message_id = await client.xadd(
                stream, {"payload": event_json}, maxlen=STREAM_MAXLEN, approximate=True
            )
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
            try:
                messages = await client.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {stream: ">"},
                    count=count,
                    block=block_ms,
                )
            except redis_exceptions.TimeoutError:
                # Blocking read expired with no data — an empty poll, not an
                # outage. Return [] so the caller loops calmly (redis-py >= 8
                # can surface the block window as a socket timeout on slow or
                # proxied connections).
                return []

            events: list[dict[str, Any]] = []
            for stream_msg in messages:
                if not isinstance(stream_msg, (list, tuple)) or len(stream_msg) != 2:
                    continue
                _stream_name, entries = stream_msg
                if not isinstance(entries, (list, tuple)):
                    continue
                for entry in entries:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    message_id, fields = entry
                    if not isinstance(fields, dict):
                        continue
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

    async def claim_pending(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int = 60_000,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Claim idle pending entries for redelivery (XAUTOCLAIM, audit #8).

        subscribe() only reads new entries ('>'), so entries delivered to a
        consumer that crashed before acking were stranded in the PEL forever.
        Call this periodically to recover them; entries returned here have
        been idle for at least ``min_idle_ms``.

        Returns:
            List of events with `event_id` and `payload` fields (same shape
            as subscribe()).
        """
        async with self.redis_manager.get_client() as client:
            try:
                await client.xgroup_create(stream, consumer_group, id="0", mkstream=True)
            except Exception as e:
                if "already exists" not in str(e):
                    raise
            result = await client.xautoclaim(
                stream,
                consumer_group,
                consumer_name,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=count,
            )
        # redis-py returns (next_start_id, claimed_entries, deleted_ids).
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) >= 2 else []
        events: list[dict[str, Any]] = []
        for entry in entries or []:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            message_id, fields = entry
            if not isinstance(fields, dict):
                continue
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
            await client.xadd(
                dlq_stream,
                {"payload": json.dumps(dlq_event)},
                maxlen=DLQ_MAXLEN,
                approximate=True,
            )
