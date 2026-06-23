"""
ODW.ai Desk — WhatsApp Business API Adapter

Handles Meta/BSP WhatsApp webhooks and message normalization.
"""

import hashlib
import hmac
from typing import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from desk.channels.base import AdapterConfig, AdapterHealthStatus, ChannelAdapter
from desk.config import get_settings
from desk.schemas.channels import InboundMessage, OutboundMessage

router = APIRouter(prefix="/api/v1/webhooks", tags=["WhatsApp"])


class WhatsAppBusinessAdapter(ChannelAdapter):
    """
    WhatsApp Business API adapter.

    Handles Meta/BSP webhook verification, signature validation,
    inbound message parsing, and outbound message delivery.
    """

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.settings = get_settings()

    async def connect(self) -> None:
        """No persistent connection for webhooks-based adapter."""
        self.update_health("healthy", True)

    async def disconnect(self) -> None:
        """No persistent connection to close."""
        self.update_health("unhealthy", False)

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Webhook adapter doesn't poll; messages arrive via HTTP."""
        # Webhook-based adapter; yield nothing
        return

    async def send(self, message: OutboundMessage) -> dict:
        """
        Send outbound message via WhatsApp Business API.

        This is a stub implementation. In production, this calls
        Meta's WhatsApp Business API to deliver the message.
        """
        self.health_status.messages_sent += 1
        return {
            "success": True,
            "channel_message_id": "wamid.stub",
            "message": "WhatsApp Business API send stubbed",
        }

    async def health_check(self) -> AdapterHealthStatus:
        """Return adapter health status."""
        return self.health_status

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        """
        Verify WhatsApp webhook HMAC-SHA256 signature.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid, False otherwise
        """
        if not signature or not self.settings.whatsapp_webhook_verify_token:
            return False

        expected = (
            "sha256="
            + hmac.new(
                self.settings.whatsapp_webhook_verify_token.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, signature)

    def parse_inbound_message(self, payload: dict) -> list[InboundMessage]:
        """
        Parse WhatsApp webhook payload into canonical InboundMessage list.

        Args:
            payload: Meta WhatsApp Cloud API webhook payload

        Returns:
            List of canonical InboundMessage objects
        """
        messages = []
        entries = payload.get("entry", [])

        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id", "")

                for message_data in value.get("messages", []):
                    message_type = message_data.get("type", "text")
                    content = ""

                    if message_type == "text":
                        content = message_data.get("text", {}).get("body", "")
                    elif message_type == "image":
                        content = "[image]"
                    elif message_type == "audio":
                        content = "[audio]"
                    elif message_type == "video":
                        content = "[video]"
                    elif message_type == "document":
                        content = "[document]"

                    from_data = message_data.get("from", {})
                    phone_number = from_data if isinstance(from_data, str) else from_data.get("id", "")

                    inbound = InboundMessage(
                        message_id=message_data.get("id", ""),
                        conversation_id=phone_number,  # Use phone number as conversation ID for WhatsApp
                        channel="whatsapp",
                        sender_identifier=phone_number,
                        sender_type="customer",
                        content=content,
                        media_urls=[],
                        metadata={
                            "phone_number_id": phone_number_id,
                            "message_type": message_type,
                            "whatsapp_message_id": message_data.get("id", ""),
                        },
                    )
                    messages.append(inbound)

        return messages


# FastAPI router for webhooks

_adapter: WhatsAppBusinessAdapter | None = None


def get_adapter() -> WhatsAppBusinessAdapter:
    """Get or create global WhatsApp adapter instance."""
    global _adapter
    if _adapter is None:
        config = AdapterConfig(
            adapter_id="whatsapp-business",
            adapter_name="WhatsApp Business API",
            channel_type="whatsapp_business",
        )
        _adapter = WhatsAppBusinessAdapter(config)
    return _adapter


@router.get("/whatsapp")
async def whatsapp_verification(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> str:
    """
    WhatsApp webhook verification endpoint.

    Meta sends a GET request to verify the webhook URL.
    """
    settings = get_settings()
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="Invalid hub.mode")

    if hub_verify_token != settings.whatsapp_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    if hub_challenge is None:
        raise HTTPException(status_code=400, detail="Missing hub.challenge")

    return hub_challenge


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
) -> JSONResponse:
    """
    WhatsApp inbound message webhook.

    Receives all WhatsApp events and processes inbound messages.
    """
    adapter = get_adapter()
    payload_bytes = await request.body()

    # Verify signature
    if not adapter.verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    messages = adapter.parse_inbound_message(payload)

    # For now, return count. In production, these would be queued to the event bus.
    return JSONResponse(
        content={
            "status": "received",
            "message_count": len(messages),
            "messages": [msg.model_dump(mode="json") for msg in messages],
        }
    )
