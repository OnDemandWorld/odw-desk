"""
ODW.ai Desk — Unit Tests for the Web-chat Channel Adapter (F-Desk-2, DC1-DC3)

Inbound: a web-chat text frame is normalized to a canonical InboundMessage
(channel="webchat") and handed to the shared MessageRouter (mocked here) which
creates/reuses the conversation + message. Outbound: replies are pushed back
over the WebSocket via the WebChatManager.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from desk.channels.webchat import (
    WebChatManager,
    build_inbound_message,
    route_webchat_message,
)
from desk.main import app


class TestBuildInboundMessage:
    def test_normalizes_to_webchat_channel(self):
        inbound = build_inbound_message("visitor-1", "Hello", message_id="m1")
        assert inbound.channel == "webchat"
        assert inbound.sender_type == "customer"
        assert inbound.sender_identifier == "visitor-1"
        # Visitor id doubles as the channel conversation id (reuse conversation).
        assert inbound.conversation_id == "visitor-1"
        assert inbound.content == "Hello"
        assert inbound.message_id == "m1"

    def test_generates_message_id_when_absent(self):
        inbound = build_inbound_message("visitor-2", "Hi")
        assert inbound.message_id.startswith("webchat-")


class TestInboundRouting:
    async def test_inbound_creates_conversation_via_router(self):
        """Inbound text is routed through MessageRouter (mocked)."""
        with patch("desk.channels.webchat.MessageRouter") as router_cls:
            instance = router_cls.return_value
            instance.route = AsyncMock(
                return_value={
                    "customer_id": "cust-1",
                    "conversation_id": "conv-1",
                    "status": "routed",
                }
            )

            db = MagicMock()
            event_bus = MagicMock()
            result = await route_webchat_message("visitor-1", "Hello", db, event_bus)

        router_cls.assert_called_once_with(db, event_bus)
        instance.route.assert_awaited_once()
        inbound = instance.route.await_args.args[0]
        assert inbound.channel == "webchat"
        assert inbound.sender_identifier == "visitor-1"
        assert inbound.content == "Hello"
        assert result["conversation_id"] == "conv-1"


class TestOutboundPush:
    async def test_push_reply_sends_over_websocket(self):
        manager = WebChatManager()
        websocket = AsyncMock()
        await manager.connect("visitor-1", websocket)
        websocket.accept.assert_awaited()

        delivered = await manager.push_reply(
            "visitor-1", "Hi there!", conversation_id="conv-1", message_id="m9"
        )

        assert delivered is True
        websocket.send_json.assert_awaited_with(
            {
                "type": "reply",
                "conversation_id": "conv-1",
                "message_id": "m9",
                "content": "Hi there!",
            }
        )

    async def test_send_to_unknown_visitor_returns_false(self):
        manager = WebChatManager()
        assert await manager.send_to_visitor("ghost", {"type": "reply"}) is False

    async def test_disconnect_removes_connection(self):
        manager = WebChatManager()
        websocket = AsyncMock()
        await manager.connect("visitor-1", websocket)
        manager.disconnect("visitor-1")
        assert await manager.send_to_visitor("visitor-1", {"x": 1}) is False


class TestWebsocketEndpoint:
    def test_endpoint_connects_and_routes_inbound_text(self):
        """Full WS handshake: connected frame, then routed ack for inbound text."""
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=MagicMock())
        cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "desk.channels.webchat.route_webchat_message",
                new=AsyncMock(
                    return_value={
                        "customer_id": "cust-1",
                        "conversation_id": "conv-1",
                        "status": "routed",
                    }
                ),
            ) as route_mock,
            patch("desk.channels.webchat.AsyncSessionLocal", return_value=cm),
            patch("desk.channels.webchat.get_event_bus", return_value=MagicMock()),
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws/chat/visitor-1") as websocket:
                connected = websocket.receive_json()
                assert connected["type"] == "connected"
                assert connected["visitor_id"] == "visitor-1"

                websocket.send_text("Hello")
                routed = websocket.receive_json()
                assert routed["type"] == "routed"
                assert routed["conversation_id"] == "conv-1"

        route_mock.assert_awaited()
        inbound_args = route_mock.await_args.args
        assert inbound_args[0] == "visitor-1"
        assert inbound_args[1] == "Hello"
