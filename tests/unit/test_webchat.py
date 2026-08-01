"""
ODW.ai Desk — Unit Tests for the Web-chat Channel Adapter (F-Desk-2, DC1-DC3)

Inbound: a web-chat text frame is normalized to a canonical InboundMessage
(channel="webchat") and handed to the shared MessageRouter (mocked here) which
creates/reuses the conversation + message. Outbound: replies are pushed back
over the WebSocket via the WebChatManager.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from desk.channels.rate_limit import SlidingWindowRateLimiter
from desk.channels.webchat import (
    WebChatManager,
    build_inbound_message,
    build_media_inbound_message,
    parse_media_frame,
    push_media,
    route_webchat_message,
)
from desk.channels.webchat import (
    manager as webchat_manager,
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

    def test_endpoint_rejects_over_limit_and_audits(self):
        """W2 — an over-limit frame is rejected (error + close) with an audit."""
        rejecting = MagicMock()
        rejecting.allow = MagicMock(return_value=False)

        with (
            patch("desk.channels.webchat.get_webchat_rate_limiter", return_value=rejecting),
            patch(
                "desk.channels.webchat._audit_rate_limit_best_effort", new=AsyncMock()
            ) as audit_mock,
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws/chat/visitor-flood") as websocket:
                connected = websocket.receive_json()
                assert connected["type"] == "connected"

                websocket.send_text("spam")
                error = websocket.receive_json()
                assert error["type"] == "error"
                assert error["code"] == "rate_limited"

        rejecting.allow.assert_called_with("visitor-flood")
        audit_mock.assert_awaited_once_with("visitor-flood")

    def test_endpoint_routes_inbound_media_frame(self):
        """W3 — a type=image JSON frame is routed with media metadata."""
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=MagicMock())
        cm.__aexit__ = AsyncMock(return_value=False)
        frame = json.dumps(
            {
                "type": "image",
                "url": "https://cdn/a.png",
                "mime": "image/png",
                "name": "a.png",
                "content": "see this",
            }
        )

        with (
            patch(
                "desk.channels.webchat.route_inbound_message",
                new=AsyncMock(return_value={"conversation_id": "conv-1", "status": "routed"}),
            ) as route_mock,
            patch("desk.channels.webchat.AsyncSessionLocal", return_value=cm),
            patch("desk.channels.webchat.get_event_bus", return_value=MagicMock()),
            patch(
                "desk.channels.webchat.get_webchat_rate_limiter",
                return_value=SlidingWindowRateLimiter(max_requests=100),
            ),
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws/chat/visitor-media") as websocket:
                websocket.receive_json()  # connected
                websocket.send_text(frame)
                routed = websocket.receive_json()
                assert routed["type"] == "routed"

        inbound = route_mock.await_args.args[0]
        assert inbound.metadata["media"]["type"] == "image"
        assert inbound.metadata["media"]["url"] == "https://cdn/a.png"
        assert inbound.media_urls == ["https://cdn/a.png"]
        assert inbound.content == "see this"


class TestParseMediaFrame:
    """W3 — inbound rich-media frame parsing (metadata only, no binary)."""

    def test_image_frame_parsed(self):
        raw = json.dumps(
            {"type": "image", "url": "https://cdn/a.png", "mime": "image/png", "name": "a.png"}
        )
        media = parse_media_frame(raw)
        assert media == {
            "type": "image",
            "url": "https://cdn/a.png",
            "mime": "image/png",
            "name": "a.png",
            "content": "",
        }

    def test_file_frame_parsed(self):
        raw = json.dumps({"type": "file", "url": "https://cdn/doc.pdf", "name": "doc.pdf"})
        media = parse_media_frame(raw)
        assert media["type"] == "file"
        assert media["url"] == "https://cdn/doc.pdf"
        assert media["name"] == "doc.pdf"

    def test_plain_text_returns_none(self):
        assert parse_media_frame("Hello there") is None

    def test_non_media_json_returns_none(self):
        assert parse_media_frame(json.dumps({"type": "text", "content": "hi"})) is None

    def test_non_object_json_returns_none(self):
        assert parse_media_frame(json.dumps([1, 2, 3])) is None


class TestBuildMediaInboundMessage:
    def test_captures_media_metadata_and_url(self):
        media = {"type": "image", "url": "https://cdn/a.png", "mime": "image/png", "name": "a.png",
                 "content": "caption"}
        inbound = build_media_inbound_message("visitor-1", media, message_id="m1")
        assert inbound.channel == "webchat"
        assert inbound.conversation_id == "visitor-1"
        assert inbound.content == "caption"
        assert inbound.media_urls == ["https://cdn/a.png"]
        assert inbound.metadata["media"] == media

    def test_missing_url_yields_empty_media_urls(self):
        media = {"type": "file", "url": None, "mime": None, "name": None, "content": ""}
        inbound = build_media_inbound_message("visitor-1", media)
        assert inbound.media_urls == []
        assert inbound.content == ""


class TestOutboundMedia:
    async def test_push_reply_with_media_attaches_metadata(self):
        manager = WebChatManager()
        websocket = AsyncMock()
        await manager.connect("visitor-1", websocket)

        media = {"type": "image", "url": "https://cdn/a.png", "mime": "image/png"}
        delivered = await manager.push_reply("visitor-1", "caption", media=media)

        assert delivered is True
        websocket.send_json.assert_awaited_with(
            {
                "type": "reply",
                "conversation_id": None,
                "message_id": None,
                "content": "caption",
                "media": media,
            }
        )

    async def test_push_reply_without_media_has_no_media_key(self):
        manager = WebChatManager()
        websocket = AsyncMock()
        await manager.connect("visitor-1", websocket)

        await manager.push_reply("visitor-1", "plain")

        payload = websocket.send_json.await_args.args[0]
        assert "media" not in payload

    async def test_push_media_module_convenience(self):
        websocket = AsyncMock()
        webchat_manager.active_connections.clear()
        await webchat_manager.connect("visitor-9", websocket)

        try:
            media = {"type": "file", "url": "https://cdn/doc.pdf", "name": "doc.pdf"}
            delivered = await push_media("visitor-9", media, content="here you go")

            assert delivered is True
            payload = websocket.send_json.await_args.args[0]
            assert payload["media"] == media
            assert payload["content"] == "here you go"
        finally:
            webchat_manager.disconnect("visitor-9")
