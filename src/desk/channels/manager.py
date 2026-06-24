"""
ODW.ai Desk — Channel Adapter Manager

Manages lifecycle, health checks, and event distribution for channel adapters.
"""

from typing import TYPE_CHECKING

from desk.channels.base import ChannelAdapter
from desk.events.redis_streams import RedisStreamsEventBus

if TYPE_CHECKING:
    from desk.utils.redis_client import RedisConnectionManager


class ChannelAdapterManager:
    """
    Manages channel adapter instances.

    Responsibilities:
    - Register/unregister adapters
    - Start/stop adapters
    - Monitor adapter health
    - Publish inbound messages to the event bus
    - Dispatch outbound messages to the correct adapter
    """

    def __init__(self, event_bus: RedisStreamsEventBus, redis_manager: "RedisConnectionManager"):
        self.event_bus = event_bus
        self.redis_manager = redis_manager
        self._adapters: dict[str, ChannelAdapter] = {}

    def register(self, adapter: ChannelAdapter) -> None:
        """Register an adapter with the manager."""
        self._adapters[adapter.config.adapter_id] = adapter

    def unregister(self, adapter_id: str) -> None:
        """Unregister an adapter."""
        if adapter_id in self._adapters:
            del self._adapters[adapter_id]

    def get_adapter(self, adapter_id: str) -> ChannelAdapter | None:
        """Get a registered adapter by ID."""
        return self._adapters.get(adapter_id)

    def list_adapters(self) -> list[ChannelAdapter]:
        """List all registered adapters."""
        return list(self._adapters.values())

    async def start_all(self) -> None:
        """Connect all enabled adapters."""
        for adapter in self._adapters.values():
            if adapter.config.enabled:
                await adapter.connect()

    async def stop_all(self) -> None:
        """Disconnect all adapters."""
        for adapter in self._adapters.values():
            await adapter.disconnect()

    async def health_checks(self) -> dict[str, dict]:
        """Run health checks on all adapters."""
        results = {}
        for adapter_id, adapter in self._adapters.items():
            health = await adapter.health_check()
            results[adapter_id] = health.model_dump()
        return results

    async def start_inbound_polling(self) -> None:
        """
        Start polling inbound messages from all adapters.

        For each adapter, subscribe to its receive() stream and publish
        messages to the event bus.
        """
        import asyncio

        async def poll_adapter(adapter: ChannelAdapter) -> None:
            try:
                async for message in adapter.receive():
                    await self.event_bus.publish(
                        "inbound.message",
                        {
                            "adapter_id": adapter.config.adapter_id,
                            "message": message.model_dump(mode="json"),
                        },
                    )
            except Exception:
                # Log error and allow reconnect logic to handle it
                pass

        tasks = [
            asyncio.create_task(poll_adapter(adapter))
            for adapter in self._adapters.values()
            if adapter.config.enabled
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
