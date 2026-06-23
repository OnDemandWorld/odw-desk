"""
ODW.ai Desk — NATS JetStream Event Bus (Stub)

Stub implementation for Kubernetes deployments.
Full implementation planned for a future sprint.
"""

from typing import Any

from desk.events.bus import EventBus


class NATSEventBus(EventBus):
    """
    NATS JetStream event bus stub.

    This is a placeholder for Kubernetes deployments where NATS is preferred
    over Redis Streams. All methods raise NotImplementedError.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        self.nats_url = nats_url

    async def connect(self) -> None:
        """Not implemented."""
        raise NotImplementedError(
            "NATS JetStream backend is not implemented in this sprint. "
            "Use Redis Streams (RedisStreamsEventBus) instead."
        )

    async def disconnect(self) -> None:
        """Not implemented."""
        raise NotImplementedError(
            "NATS JetStream backend is not implemented in this sprint. "
            "Use Redis Streams (RedisStreamsEventBus) instead."
        )

    async def publish(self, stream: str, event: dict[str, Any]) -> str:
        """Not implemented."""
        raise NotImplementedError(
            "NATS JetStream backend is not implemented in this sprint. "
            "Use Redis Streams (RedisStreamsEventBus) instead."
        )

    async def subscribe(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        """Not implemented."""
        raise NotImplementedError(
            "NATS JetStream backend is not implemented in this sprint. "
            "Use Redis Streams (RedisStreamsEventBus) instead."
        )

    async def acknowledge(self, stream: str, consumer_group: str, message_id: str) -> None:
        """Not implemented."""
        raise NotImplementedError(
            "NATS JetStream backend is not implemented in this sprint. "
            "Use Redis Streams (RedisStreamsEventBus) instead."
        )

    async def dead_letter(self, stream: str, event: dict[str, Any], reason: str) -> None:
        """Not implemented."""
        raise NotImplementedError(
            "NATS JetStream backend is not implemented in this sprint. "
            "Use Redis Streams (RedisStreamsEventBus) instead."
        )
