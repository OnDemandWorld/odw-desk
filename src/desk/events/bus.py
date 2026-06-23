"""
ODW.ai Desk — Event Bus Abstract Interface

Provides the contract for all event bus implementations.
"""

from abc import ABC, abstractmethod
from typing import Any


class EventBus(ABC):
    """
    Abstract event bus interface.

    All event bus implementations (Redis Streams, NATS JetStream) must
    implement this interface.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the event bus."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the event bus."""
        pass

    @abstractmethod
    async def publish(self, stream: str, event: dict[str, Any]) -> str:
        """
        Publish an event to a stream.

        Args:
            stream: Stream name
            event: Event payload as a dictionary

        Returns:
            Message ID
        """
        pass

    @abstractmethod
    async def subscribe(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        """
        Read events from a stream as part of a consumer group.

        Args:
            stream: Stream name
            consumer_group: Consumer group name
            consumer_name: Consumer name
            count: Maximum number of messages to read
            block_ms: Blocking timeout in milliseconds

        Returns:
            List of event dictionaries with additional `event_id` field
        """
        pass

    @abstractmethod
    async def acknowledge(self, stream: str, consumer_group: str, message_id: str) -> None:
        """
        Acknowledge a message so it is not redelivered.

        Args:
            stream: Stream name
            consumer_group: Consumer group name
            message_id: Message ID to acknowledge
        """
        pass

    @abstractmethod
    async def dead_letter(self, stream: str, event: dict[str, Any], reason: str) -> None:
        """
        Move a failed event to the dead-letter queue.

        Args:
            stream: Original stream name
            event: Event payload
            reason: Reason for failure
        """
        pass
