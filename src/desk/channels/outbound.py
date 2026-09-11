"""
ODW.ai Desk — Outbound Dispatcher

Routes outbound messages to the correct channel adapter and handles delivery.
"""

import structlog

from desk.channels.base import ChannelAdapter, OutboundMessage
from desk.channels.manager import ChannelAdapterManager

logger = structlog.get_logger()


class OutboundDispatcher:
    """
    Outbound message dispatcher.

    Routes outbound messages to the appropriate channel adapter based on
    the message's channel type. Handles retry logic and delivery tracking.
    """

    def __init__(self, channel_manager: ChannelAdapterManager):
        self.channel_manager = channel_manager

    async def dispatch(self, message: OutboundMessage) -> dict:
        """
        Dispatch an outbound message to the correct channel adapter.

        Args:
            message: Normalized outbound message

        Returns:
            Delivery result
        """
        # Find adapter by channel type
        adapter = self._find_adapter(message.channel)

        if adapter is None:
            logger.error(
                "No adapter found for channel",
                channel=message.channel,
                conversation_id=message.conversation_id,
            )
            return {
                "success": False,
                "error": f"No adapter found for channel: {message.channel}",
            }

        try:
            result = await adapter.send(message)
            logger.info(
                "Outbound message dispatched",
                channel=message.channel,
                conversation_id=message.conversation_id,
                result=result,
            )
            return result
        except Exception as e:
            logger.error(
                "Failed to dispatch outbound message",
                channel=message.channel,
                conversation_id=message.conversation_id,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    def _find_adapter(self, channel: str) -> ChannelAdapter | None:
        """Find a registered adapter for the given channel."""
        adapters = self.channel_manager.list_adapters()

        # 1. Exact match on adapter channel type
        for adapter in adapters:
            if adapter.config.channel_type == channel:
                return adapter

        # 2. Canonical channel aliases: adapters registered under a provider-
        #    specific channel_type (e.g. "whatsapp_business") serve the
        #    canonical customer-facing channel ("whatsapp"). An explicit map
        #    replaces the previous blind prefix match, which would let any
        #    similarly-prefixed adapter (e.g. "webchat_widget") steal traffic.
        aliases = {
            "whatsapp": ("whatsapp_business", "whatsapp_baileys"),
        }.get(channel, ())
        if aliases:
            for adapter in adapters:
                if adapter.config.channel_type in aliases:
                    return adapter

        return None
