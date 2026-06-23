"""
ODW.ai Desk — Mock Channel Adapter

Simple mock adapter for testing the channel adapter framework.
"""

import asyncio
from typing import AsyncIterator

from desk.channels.base import AdapterConfig, AdapterHealthStatus, ChannelAdapter
from desk.schemas.channels import InboundMessage, OutboundMessage


class MockChannelAdapter(ChannelAdapter):
    """
    Mock channel adapter for testing.

    Simulates receiving and sending messages without connecting to a real service.
    """

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self._connected = False
        self._messages: list[InboundMessage] = []

    async def connect(self) -> None:
        """Simulate connection."""
        self._connected = True
        self.update_health("healthy", True)

    async def disconnect(self) -> None:
        """Simulate disconnection."""
        self._connected = False
        self.update_health("unhealthy", False)

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Yield mock inbound messages."""
        while self._connected:
            if self._messages:
                yield self._messages.pop(0)
            await asyncio.sleep(0.1)

    async def send(self, message: OutboundMessage) -> dict:
        """Simulate sending an outbound message."""
        self.health_status.messages_sent += 1
        return {"success": True, "channel_message_id": "mock-message-id"}

    async def health_check(self) -> AdapterHealthStatus:
        """Return mock health status."""
        return self.health_status

    def queue_message(self, message: InboundMessage) -> None:
        """Queue a message to be received."""
        self._messages.append(message)
        self.health_status.messages_received += 1
