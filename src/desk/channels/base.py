"""
ODW.ai Desk — Channel Adapter Base

Abstract base class and types for all channel adapters.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, Field

from desk.schemas.channels import InboundMessage, OutboundMessage


class AdapterHealthStatus(BaseModel):
    """Health status of a channel adapter."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Health status")
    connected: bool = Field(..., description="Whether adapter is connected")
    last_connected_at: datetime | None = Field(None, description="Last connection timestamp")
    last_error: str | None = Field(None, description="Last error message")
    messages_sent: int = Field(0, description="Total messages sent")
    messages_received: int = Field(0, description="Total messages received")


class AdapterConfig(BaseModel):
    """Base configuration for all channel adapters."""

    adapter_id: str = Field(..., description="Unique adapter identifier")
    adapter_name: str = Field(..., description="Human-readable adapter name")
    channel_type: str = Field(..., description="Channel type (whatsapp_business, whatsapp_baileys, etc.)")
    enabled: bool = Field(True, description="Whether adapter is enabled")
    credentials: dict[str, Any] = Field(default_factory=dict, description="Channel-specific credentials")
    settings: dict[str, Any] = Field(default_factory=dict, description="Channel-specific settings")
    reconnect_policy: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "exponential_backoff",
            "max_attempts": 10,
            "base_delay_seconds": 1,
            "max_delay_seconds": 300,
        },
        description="Reconnection policy",
    )


class ChannelAdapter(ABC):
    """
    Abstract base class for all channel adapters.

    Each channel (WhatsApp Business, Baileys, web chat, email, etc.)
    implements this interface.
    """

    def __init__(self, config: AdapterConfig):
        self.config = config
        self.health_status = AdapterHealthStatus(status="unhealthy", connected=False)

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to external channel."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close connection to external channel."""
        pass

    @abstractmethod
    async def receive(self) -> AsyncIterator[InboundMessage]:
        """
        Yield normalized inbound messages from the channel.

        This is typically an infinite loop that yields messages as they arrive.
        """
        pass

    @abstractmethod
    async def send(self, message: OutboundMessage) -> dict[str, Any]:
        """
        Deliver an outbound message to the channel.

        Args:
            message: Normalized outbound message

        Returns:
            Delivery result with success status and channel message ID
        """
        pass

    @abstractmethod
    async def health_check(self) -> AdapterHealthStatus:
        """
        Return adapter health and connection status.

        Returns:
            AdapterHealthStatus with current state
        """
        pass

    async def reconnect(self) -> None:
        """Reconnect to the channel."""
        await self.disconnect()
        await self.connect()

    async def on_disconnect(self) -> None:
        """Callback for when adapter disconnects unexpectedly."""
        self.health_status.connected = False

    def update_health(
        self,
        status: Literal["healthy", "degraded", "unhealthy"],
        connected: bool,
        last_error: str | None = None,
    ) -> None:
        """Update adapter health status."""
        self.health_status.status = status
        self.health_status.connected = connected
        if last_error:
            self.health_status.last_error = last_error
        if connected:
            self.health_status.last_connected_at = datetime.utcnow()
