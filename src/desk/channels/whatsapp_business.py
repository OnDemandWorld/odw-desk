"""
ODW.ai Desk — WhatsApp Business API Adapter

Handles Meta/BSP WhatsApp webhooks and message normalization.
"""

import hashlib
import hmac
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from desk.channels.base import AdapterConfig, AdapterHealthStatus, ChannelAdapter
from desk.config import get_settings
from desk.dependencies import get_db, get_event_bus
from desk.observability.metrics import MESSAGES_RECEIVED
from desk.router.message_router import MessageRouter
from desk.schemas.channels import InboundMessage, OutboundMessage

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["WhatsApp"])

# Default Meta Graph API base URL for the WhatsApp Cloud API.
DEFAULT_GRAPH_API_BASE_URL = "https://graph.facebook.com/v19.0"


class WhatsAppBusinessAdapter(ChannelAdapter):
    """
    WhatsApp Business API adapter.

    Handles Meta/BSP webhook verification, signature validation,
    inbound message parsing, and outbound message delivery.
    """

    def __init__(self, config: AdapterConfig, graph_api_base_url: str | None = None):
        super().__init__(config)
        self.settings = get_settings()
        # Graph API base URL is injectable so tests can point it at a mock server.
        base = graph_api_base_url or self.settings.whatsapp_graph_api_base_url
        self.graph_api_base_url = (base or DEFAULT_GRAPH_API_BASE_URL).rstrip("/")

    async def connect(self) -> None:
        """No persistent connection for webhooks-based adapter."""
        self.update_health("healthy", True)

    async def disconnect(self) -> None:
        """No persistent connection to close."""
        self.update_health("unhealthy", False)

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Webhook adapter doesn't poll; messages arrive via HTTP."""
        # Webhook-based adapter; yield nothing
        # Make it an async generator that never yields
        if False:
            yield  # noqa: PLW0127

    async def send(self, message: OutboundMessage) -> dict:
        """
        Send outbound message via WhatsApp Business API.

        If a WhatsApp access token and phone number ID are configured, this
        will call Meta's WhatsApp Cloud API. In development, it logs the
        message and returns a stubbed success so the end-to-end pipeline can
        be exercised without real credentials.
        """
        self.health_status.messages_sent += 1

        access_token = self.settings.whatsapp_access_token
        phone_number_id = self.settings.whatsapp_phone_number_id

        if not access_token or not phone_number_id:
            logger.warning(
                "WhatsApp Business API credentials not configured; sending is stubbed",
                recipient=message.recipient_identifier,
                conversation_id=message.conversation_id,
            )
            return {
                "success": True,
                "channel_message_id": "wamid.stub",
                "message": "WhatsApp Business API send stubbed (no credentials)",
            }

        # Real Meta WhatsApp Cloud API call.
        url = f"{self.graph_api_base_url}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.recipient_identifier,
            "type": "text",
            "text": {"body": message.content},
        }

        logger.info(
            "Sending WhatsApp message",
            recipient=message.recipient_identifier,
            conversation_id=message.conversation_id,
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                result = response.json()

            channel_message_id = None
            messages = result.get("messages") or []
            if messages:
                channel_message_id = messages[0].get("id")

            return {
                "success": True,
                "channel_message_id": channel_message_id,
                "message": "WhatsApp message sent",
            }
        except httpx.HTTPStatusError as exc:
            logger.error(
                "WhatsApp Cloud API returned an error",
                status_code=exc.response.status_code,
                error=exc.response.text,
                recipient=message.recipient_identifier,
            )
            return {
                "success": False,
                "channel_message_id": None,
                "error": f"Graph API error: {exc.response.status_code}",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "WhatsApp send failed",
                error=str(exc),
                recipient=message.recipient_identifier,
            )
            return {
                "success": False,
                "channel_message_id": None,
                "error": str(exc),
            }

    async def health_check(self) -> AdapterHealthStatus:
        """Return adapter health status."""
        return self.health_status

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        """
        Verify WhatsApp webhook HMAC-SHA256 signature.

        Meta signs the raw request body with the WhatsApp *app secret*, sending
        the result as ``X-Hub-Signature-256: sha256=<hex>``. The webhook verify
        token is NOT the signing key — it is only used for the GET URL handshake.

        When no app secret is configured, signature verification is skipped (and
        a warning is logged) so local development without credentials still works.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if the signature is valid (or verification is skipped), False otherwise
        """
        app_secret = self.settings.whatsapp_app_secret
        if not app_secret:
            logger.warning(
                "whatsapp_app_secret not configured; skipping webhook signature "
                "verification (development only — set WHATSAPP_APP_SECRET in production)"
            )
            return True

        if not signature:
            return False

        expected = (
            "sha256="
            + hmac.new(
                app_secret.encode(),
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

                    # Parse WhatsApp Unix timestamp if present, otherwise use now
                    ts = message_data.get("timestamp")
                    try:
                        timestamp = datetime.fromtimestamp(int(ts), tz=UTC) if ts else datetime.now(tz=UTC)
                    except (TypeError, ValueError):
                        timestamp = datetime.now(tz=UTC)

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
                        timestamp=timestamp,
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
            enabled=True,
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
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
) -> JSONResponse:
    """
    WhatsApp inbound message webhook.

    Receives all WhatsApp events, normalizes them, persists them to the
    database, and publishes a routing event to the event bus for AI processing.
    """
    adapter = get_adapter()
    payload_bytes = await request.body()

    # Verify signature
    if not adapter.verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    messages = adapter.parse_inbound_message(payload)

    # Observability: count inbound messages received on this channel.
    if messages:
        MESSAGES_RECEIVED.labels(channel="whatsapp", status="received").inc(len(messages))

    # Route each inbound message through the core pipeline
    event_bus = get_event_bus()
    message_router = MessageRouter(db, event_bus)
    routed = []
    for message in messages:
        result = await message_router.route(message)
        routed.append(result)

    return JSONResponse(
        content={
            "status": "received",
            "message_count": len(messages),
            "routed": routed,
            "messages": [msg.model_dump(mode="json") for msg in messages],
        }
    )
