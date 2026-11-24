"""
ODW.ai Desk — Outbound Dispatcher

Routes outbound messages to the correct channel adapter and handles delivery.
"""

import asyncio

import structlog

from desk.channels.base import ChannelAdapter, OutboundMessage
from desk.channels.manager import ChannelAdapterManager

logger = structlog.get_logger()


class OutboundDispatcher:
    """
    Outbound message dispatcher.

    Routes outbound messages to the appropriate channel adapter based on
    the message's channel type. Retries transient send failures with bounded
    exponential backoff (audit #6). Callers MUST inspect ``result["success"]``
    — a failed delivery must not be acknowledged as done.
    """

    MAX_SEND_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = 0.5

    def __init__(self, channel_manager: ChannelAdapterManager):
        self.channel_manager = channel_manager

    async def dispatch(self, message: OutboundMessage) -> dict:
        """
        Dispatch an outbound message to the correct channel adapter.

        Args:
            message: Normalized outbound message

        Returns:
            Delivery result; ``success`` is False when every attempt failed.
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

        result: dict = {"success": False, "error": "not attempted"}
        for attempt in range(1, self.MAX_SEND_ATTEMPTS + 1):
            try:
                result = await adapter.send(message)
            except Exception as e:
                logger.error(
                    "Failed to dispatch outbound message",
                    channel=message.channel,
                    conversation_id=message.conversation_id,
                    attempt=attempt,
                    error=str(e),
                )
                result = {"success": False, "error": str(e)}
            if result.get("success"):
                logger.info(
                    "Outbound message dispatched",
                    channel=message.channel,
                    conversation_id=message.conversation_id,
                    attempt=attempt,
                    result=result,
                )
                return result
            if attempt < self.MAX_SEND_ATTEMPTS:
                logger.warning(
                    "Outbound send failed; retrying",
                    channel=message.channel,
                    conversation_id=message.conversation_id,
                    attempt=attempt,
                    error=result.get("error"),
                )
                await asyncio.sleep(self.RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))

        logger.error(
            "Outbound delivery failed after all retries",
            channel=message.channel,
            conversation_id=message.conversation_id,
            attempts=self.MAX_SEND_ATTEMPTS,
            error=result.get("error"),
        )
        return result

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
