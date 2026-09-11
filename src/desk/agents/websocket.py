"""
ODW.ai Desk — Agent WebSocket (AGENT-002)

Real-time updates for human agents via WebSocket connections.
Broadcasts conversation events to connected agents.
"""

import hmac
import json
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from desk.config import get_settings
from desk.models.agent import Agent

logger = structlog.get_logger()

router = APIRouter(tags=["Agent WebSocket"])


class ConnectionManager:
    """
    Manages WebSocket connections for real-time agent updates.

    Handles connection lifecycle, message broadcasting, and agent session
    tracking. An agent may hold several simultaneous connections (multiple
    tabs/devices); each socket is tracked independently so closing one never
    tears down another.
    """

    def __init__(self) -> None:
        self.active_connections: dict[UUID, set[WebSocket]] = {}
        self.agent_subscriptions: dict[UUID, set[str]] = {}  # agent_id -> set of conversation_ids

    async def connect(self, agent_id: UUID, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.setdefault(agent_id, set()).add(websocket)
        self.agent_subscriptions.setdefault(agent_id, set())
        logger.info("Agent WebSocket connected", agent_id=str(agent_id))

    def disconnect(self, agent_id: UUID, websocket: WebSocket) -> None:
        """Remove one specific WebSocket connection for an agent."""
        sockets = self.active_connections.get(agent_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                del self.active_connections[agent_id]
                # Only drop subscriptions with the agent's last connection.
                self.agent_subscriptions.pop(agent_id, None)
        logger.info("Agent WebSocket disconnected", agent_id=str(agent_id))

    async def send_to_agent(self, agent_id: UUID, message: dict[str, Any]) -> None:
        """Send a message to every live connection of an agent."""
        for websocket in list(self.active_connections.get(agent_id, ())):
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("Failed to send to agent", agent_id=str(agent_id), error=str(e))
                self.disconnect(agent_id, websocket)

    async def broadcast_to_agents(
        self,
        message: dict[str, Any],
        conversation_id: str | None = None,
    ) -> None:
        """
        Broadcast a message to agents.

        If conversation_id is provided, only send to agents subscribed to that conversation.
        Otherwise, broadcast to all connected agents.
        """
        if conversation_id:
            # Send to agents subscribed to this conversation
            target_agents = [
                agent_id
                for agent_id, subs in self.agent_subscriptions.items()
                if conversation_id in subs
            ]
        else:
            # Broadcast to all agents
            target_agents = list(self.active_connections.keys())

        for agent_id in target_agents:
            await self.send_to_agent(agent_id, message)

    def subscribe_agent(self, agent_id: UUID, conversation_id: str) -> None:
        """Subscribe an agent to conversation updates."""
        if agent_id in self.agent_subscriptions:
            self.agent_subscriptions[agent_id].add(conversation_id)
            logger.debug(
                "Agent subscribed to conversation",
                agent_id=str(agent_id),
                conversation_id=conversation_id,
            )

    def unsubscribe_agent(self, agent_id: UUID, conversation_id: str) -> None:
        """Unsubscribe an agent from conversation updates."""
        if agent_id in self.agent_subscriptions:
            self.agent_subscriptions[agent_id].discard(conversation_id)


# Global connection manager
connection_manager = ConnectionManager()


def _websocket_authenticated(websocket: WebSocket) -> bool:
    """
    Handshake authentication for the agent WebSocket.

    Mirrors the REST API-key guard: when ``DESK_API_KEY`` is unset the
    endpoint stays open (dev / backward compatible); when set, the client must
    present the key via ``?token=``, ``X-API-Key``, or ``Authorization: Bearer``
    (browsers cannot set custom WS headers, hence the query param).
    """
    expected = (get_settings().desk_api_key or "").strip()
    if not expected:
        return True

    supplied = (
        websocket.query_params.get("token")
        or websocket.headers.get("x-api-key")
        or None
    )
    if supplied is None:
        auth = websocket.headers.get("authorization") or ""
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    if not supplied:
        return False

    try:
        return hmac.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        )
    except (UnicodeEncodeError, AttributeError):
        return False


@router.websocket("/ws/agents/{agent_id}")
async def agent_websocket(websocket: WebSocket, agent_id: UUID) -> None:
    """
    WebSocket endpoint for real-time agent updates.

    Agents receive real-time notifications for:
    - New messages in subscribed conversations
    - Conversation state changes
    - Escalation events
    - SLA breaches

    Authentication follows the REST API-key guard: when ``DESK_API_KEY`` is
    configured the handshake must present it (`?token=` / `X-API-Key` /
    `Authorization: Bearer`), otherwise the socket is closed with 4401.
    """
    if not _websocket_authenticated(websocket):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    # Verify agent exists
    from desk.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        query = select(Agent).where(Agent.id == agent_id)
        result = await db.execute(query)
        agent = result.scalar_one_or_none()

        if not agent:
            await websocket.close(code=4001, reason="Agent not found")
            return

    # Connect
    await connection_manager.connect(agent_id, websocket)

    try:
        while True:
            # Receive messages from agent (subscription requests, etc.)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        connection_manager.subscribe_agent(agent_id, conversation_id)
                        await websocket.send_json({
                            "type": "subscription_confirmed",
                            "conversation_id": conversation_id,
                        })

                elif action == "unsubscribe":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        connection_manager.unsubscribe_agent(agent_id, conversation_id)
                        await websocket.send_json({
                            "type": "unsubscription_confirmed",
                            "conversation_id": conversation_id,
                        })

                elif action == "ping":
                    await websocket.send_json({"type": "pong"})

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        connection_manager.disconnect(agent_id, websocket)
    except Exception as e:
        logger.error("WebSocket error", agent_id=str(agent_id), error=str(e))
        connection_manager.disconnect(agent_id, websocket)


async def broadcast_new_message(
    conversation_id: str,
    message_data: dict[str, Any],
) -> None:
    """Broadcast a new message event to subscribed agents."""
    await connection_manager.broadcast_to_agents(
        {
            "type": "new_message",
            "conversation_id": conversation_id,
            "message": message_data,
        },
        conversation_id=conversation_id,
    )


async def broadcast_conversation_update(
    conversation_id: str,
    update_data: dict[str, Any],
) -> None:
    """Broadcast a conversation update event to subscribed agents."""
    await connection_manager.broadcast_to_agents(
        {
            "type": "conversation_update",
            "conversation_id": conversation_id,
            "update": update_data,
        },
        conversation_id=conversation_id,
    )


async def broadcast_escalation(
    conversation_id: str,
    escalation_data: dict[str, Any],
) -> None:
    """Broadcast an escalation event to all agents."""
    await connection_manager.broadcast_to_agents(
        {
            "type": "escalation",
            "conversation_id": conversation_id,
            "escalation": escalation_data,
        },
    )


async def broadcast_sla_breach(
    conversation_id: str,
    breach_data: dict[str, Any],
) -> None:
    """Broadcast an SLA breach event to relevant agents."""
    await connection_manager.broadcast_to_agents(
        {
            "type": "sla_breach",
            "conversation_id": conversation_id,
            "breach": breach_data,
        },
        conversation_id=conversation_id,
    )
