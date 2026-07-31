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

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from desk.db import AsyncSessionLocal
from desk.dependencies import get_event_bus
from desk.router.message_router import MessageRouter
from desk.schemas.channels import InboundMessage

logger = structlog.get_logger()

router = APIRouter(tags=["WebChat"])

WEBCHAT_CHANNEL = "webchat"


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
    ) -> bool:
        """Push an outbound reply message envelope to a visitor."""
        return await self.send_to_visitor(
            visitor_id,
            {
                "type": "reply",
                "conversation_id": conversation_id,
                "message_id": message_id,
                "content": content,
            },
        )


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
    message_router = MessageRouter(db, event_bus)
    return await message_router.route(inbound)


async def push_reply(visitor_id: str, content: str, **kwargs: Any) -> bool:
    """Module-level convenience to push an outbound reply to a visitor."""
    return await manager.push_reply(visitor_id, content, **kwargs)


@router.websocket("/ws/chat/{visitor_id}")
async def webchat_endpoint(websocket: WebSocket, visitor_id: str) -> None:
    """
    WebSocket endpoint for browser-based chat.

    Inbound text frames are routed through the shared pipeline; each routed
    message is acknowledged with a ``routed`` envelope carrying the resolved
    conversation id. Outbound AI/agent replies are pushed via ``push_reply``.
    """
    await manager.connect(visitor_id, websocket)
    await websocket.send_json({"type": "connected", "visitor_id": visitor_id})

    try:
        while True:
            text = await websocket.receive_text()
            if not text.strip():
                continue

            try:
                async with AsyncSessionLocal() as db:
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
