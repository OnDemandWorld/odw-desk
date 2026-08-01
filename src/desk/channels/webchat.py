"""
ODW.ai Desk — Web-chat Channel Adapter (F-Desk-2)

WebSocket web-chat channel that shares the existing conversation/agent pipeline
with WhatsApp. Inbound visitor text is normalized to the canonical
:class:`InboundMessage` (``channel="webchat"``) and handed to the existing
:class:`MessageRouter`, which resolves/creates the customer + conversation and
persists the message. Outbound replies are pushed back over the WebSocket via
the :class:`WebChatManager`.

Endpoint: ``WS /ws/chat/{visitor_id}`` — ``visitor_id`` is an opaque browser
identifier used as both the sender identifier and the channel conversation id,
so a returning visitor reuses the same conversation.
"""

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from desk.channels.rate_limit import get_webchat_rate_limiter
from desk.compliance.engine import ComplianceEngine
from desk.db import AsyncSessionLocal
from desk.dependencies import get_event_bus
from desk.router.message_router import MessageRouter
from desk.schemas.channels import InboundMessage

logger = structlog.get_logger()

router = APIRouter(tags=["WebChat"])

WEBCHAT_CHANNEL = "webchat"

# Inbound frame types treated as rich media (metadata only — no binary storage).
MEDIA_FRAME_TYPES = ("image", "file")


class WebChatManager:
    """
    Manages web-chat WebSocket connections keyed by visitor id.

    Tracks live sockets and pushes outbound reply envelopes back to visitors.
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, visitor_id: str, websocket: WebSocket) -> None:
        """Accept and register a visitor WebSocket connection."""
        await websocket.accept()
        self.active_connections[visitor_id] = websocket
        logger.info("Web-chat connected", visitor_id=visitor_id)

    def disconnect(self, visitor_id: str) -> None:
        """Remove a visitor WebSocket connection."""
        if visitor_id in self.active_connections:
            del self.active_connections[visitor_id]
            logger.info("Web-chat disconnected", visitor_id=visitor_id)

    async def send_to_visitor(self, visitor_id: str, payload: dict[str, Any]) -> bool:
        """
        Send an arbitrary JSON payload to a connected visitor.

        Returns True when delivered, False when the visitor is not connected
        (or the send failed, in which case the socket is dropped).
        """
        websocket = self.active_connections.get(visitor_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(payload)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Web-chat send failed", visitor_id=visitor_id, error=str(exc))
            self.disconnect(visitor_id)
            return False

    async def push_reply(
        self,
        visitor_id: str,
        content: str,
        conversation_id: str | None = None,
        message_id: str | None = None,
        media: dict[str, Any] | None = None,
    ) -> bool:
        """
        Push an outbound reply envelope to a visitor.

        When ``media`` is supplied (e.g. ``{"type": "image", "url": ..., "mime":
        ..., "name": ...}``) it is attached as metadata so rich-media replies are
        delivered over the WebSocket without any binary payload.
        """
        payload: dict[str, Any] = {
            "type": "reply",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "content": content,
        }
        if media:
            payload["media"] = media
        return await self.send_to_visitor(visitor_id, payload)


# Global connection manager (mirrors desk.agents.websocket pattern).
manager = WebChatManager()


def build_inbound_message(visitor_id: str, text: str, message_id: str | None = None) -> InboundMessage:
    """
    Normalize a web-chat text frame into the canonical inbound message.

    The visitor id doubles as the sender identifier and the channel
    conversation id so repeat visitors reuse a single conversation.
    """
    return InboundMessage(
        message_id=message_id or f"webchat-{uuid.uuid4().hex}",
        conversation_id=visitor_id,
        channel=WEBCHAT_CHANNEL,
        sender_identifier=visitor_id,
        sender_type="customer",
        content=text,
        media_urls=[],
        metadata={"channel": WEBCHAT_CHANNEL},
    )


async def route_webchat_message(
    visitor_id: str,
    text: str,
    db: Any,
    event_bus: Any,
    message_id: str | None = None,
) -> dict[str, Any]:
    """
    Route an inbound web-chat message through the shared MessageRouter.

    Creates/reuses the customer + conversation and persists the message exactly
    like the WhatsApp path. Separated from the socket handler for testability.
    """
    inbound = build_inbound_message(visitor_id, text, message_id=message_id)
    return await route_inbound_message(inbound, db, event_bus)


async def route_inbound_message(inbound: InboundMessage, db: Any, event_bus: Any) -> dict[str, Any]:
    """Route an already-built inbound message through the shared MessageRouter."""
    message_router = MessageRouter(db, event_bus)
    return await message_router.route(inbound)


def parse_media_frame(raw: str) -> dict[str, Any] | None:
    """
    Parse an inbound rich-media frame, returning normalized metadata or None.

    A media frame is a JSON object whose ``type`` is ``image`` or ``file``::

        {"type": "image", "url": "https://…/a.png",
         "mime": "image/png", "name": "a.png", "content": "optional caption"}

    Only url/mime/name (plus an optional caption) are captured — no binary is
    stored. Plain text or any non-media JSON returns None so the caller falls
    back to the regular text path.
    """
    try:
        frame = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(frame, dict):
        return None

    frame_type = str(frame.get("type") or "").lower()
    if frame_type not in MEDIA_FRAME_TYPES:
        return None

    url = frame.get("url")
    return {
        "type": frame_type,
        "url": str(url) if url is not None else None,
        "mime": frame.get("mime"),
        "name": frame.get("name"),
        "content": frame.get("content") or "",
    }


def build_media_inbound_message(
    visitor_id: str,
    media: dict[str, Any],
    message_id: str | None = None,
) -> InboundMessage:
    """
    Normalize a parsed rich-media frame into the canonical inbound message.

    The media url/mime/name are carried in ``metadata["media"]`` (and the url in
    ``media_urls``); the optional caption becomes the message content.
    """
    url = media.get("url")
    return InboundMessage(
        message_id=message_id or f"webchat-{uuid.uuid4().hex}",
        conversation_id=visitor_id,
        channel=WEBCHAT_CHANNEL,
        sender_identifier=visitor_id,
        sender_type="customer",
        content=media.get("content") or "",
        media_urls=[url] if url else [],
        metadata={"channel": WEBCHAT_CHANNEL, "media": media},
    )


async def _audit_rate_limit_best_effort(visitor_id: str) -> None:
    """
    Record a best-effort audit entry when a visitor is rate-limited.

    Never raises — auditing must not interfere with the rejection path. The
    visitor id is not a UUID, so a synthetic resource id is used and the visitor
    is referenced in ``details``.
    """
    try:
        async with AsyncSessionLocal() as db:
            engine = ComplianceEngine(db)
            await engine.log_audit_event(
                action="rate_limited",
                actor_id=visitor_id,
                actor_type="system",
                resource_type="webchat_visitor",
                resource_id=str(uuid.uuid4()),
                details={"visitor_id": visitor_id, "channel": WEBCHAT_CHANNEL},
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - best-effort, never raise
        logger.warning(
            "Web-chat rate-limit audit failed (best-effort)",
            visitor_id=visitor_id,
            error=str(exc),
        )


async def push_reply(visitor_id: str, content: str, **kwargs: Any) -> bool:
    """Module-level convenience to push an outbound reply to a visitor."""
    return await manager.push_reply(visitor_id, content, **kwargs)


async def push_media(
    visitor_id: str,
    media: dict[str, Any],
    content: str = "",
    **kwargs: Any,
) -> bool:
    """Module-level convenience to push an outbound rich-media reply (metadata)."""
    return await manager.push_reply(visitor_id, content, media=media, **kwargs)


@router.websocket("/ws/chat/{visitor_id}")
async def webchat_endpoint(websocket: WebSocket, visitor_id: str) -> None:
    """
    WebSocket endpoint for browser-based chat.

    Inbound frames are rate-limited per visitor (V1.4 F-4); over-limit frames are
    rejected and the socket closed with a best-effort audit record. Plain-text
    frames and rich-media frames (``type=image|file`` JSON) are routed through the
    shared pipeline, and each routed message is acknowledged with a ``routed``
    envelope carrying the resolved conversation id. Outbound AI/agent replies are
    pushed via ``push_reply`` / ``push_media``.
    """
    await manager.connect(visitor_id, websocket)
    await websocket.send_json({"type": "connected", "visitor_id": visitor_id})

    limiter = get_webchat_rate_limiter()

    try:
        while True:
            text = await websocket.receive_text()
            if not text.strip():
                continue

            # Per-visitor inbound rate limiting (best-effort abuse mitigation).
            if not limiter.allow(visitor_id):
                logger.warning("Web-chat rate limit exceeded", visitor_id=visitor_id)
                await _audit_rate_limit_best_effort(visitor_id)
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "rate_limited",
                        "message": "Too many messages; please slow down.",
                    }
                )
                await websocket.close(code=1008)
                break

            try:
                media = parse_media_frame(text)
                async with AsyncSessionLocal() as db:
                    if media is not None:
                        inbound = build_media_inbound_message(visitor_id, media)
                        result = await route_inbound_message(inbound, db, get_event_bus())
                    else:
                        result = await route_webchat_message(
                            visitor_id, text, db, get_event_bus()
                        )
                await websocket.send_json({"type": "routed", **result})
            except Exception as exc:  # noqa: BLE001
                logger.error("Web-chat routing failed", visitor_id=visitor_id, error=str(exc))
                await websocket.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        manager.disconnect(visitor_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Web-chat socket error", visitor_id=visitor_id, error=str(exc))
        manager.disconnect(visitor_id)
