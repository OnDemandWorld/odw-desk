"""
ODW.ai Desk — Unit Tests for Web-chat Enhancements (V1.6 F-4, DC1/DC2)

DC1: read-receipt frames (``{type:'read', message_id}``) set ``Message.read_at``
and are acknowledged over the socket. DC2: rich-media metadata is persisted onto
the message record (via the shared MessageRouter) instead of living in memory.
Both are backward compatible: no read event -> read_at stays null; no media ->
no media key persisted.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from desk.channels.webchat import mark_message_read, parse_media_frame, parse_read_frame
from desk.main import app
from desk.models.message import Message
from desk.router.message_router import MessageRouter
from desk.schemas.channels import InboundMessage


class TestParseReadFrame:
    def test_read_frame_parsed(self):
        raw = json.dumps({"type": "read", "message_id": "m1"})
        assert parse_read_frame(raw) == "m1"

    def test_read_frame_case_insensitive_type(self):
        raw = json.dumps({"type": "READ", "message_id": "m2"})
        assert parse_read_frame(raw) == "m2"

    def test_missing_message_id_returns_none(self):
        assert parse_read_frame(json.dumps({"type": "read"})) is None

    def test_non_read_frame_returns_none(self):
        assert parse_read_frame(json.dumps({"type": "image", "url": "x"})) is None

    def test_plain_text_returns_none(self):
        assert parse_read_frame("hello") is None

    def test_non_object_json_returns_none(self):
        assert parse_read_frame(json.dumps([1, 2])) is None


class TestMarkMessageRead:
    def _db_returning(self, message):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=message)
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()
        return db

    async def test_sets_read_at_by_channel_message_id(self):
        message = Message(content="hi", sender_type="customer", channel_message_id="m1")
        assert message.read_at is None
        db = self._db_returning(message)

        out = await mark_message_read(db, "m1")

        assert out is message
        assert message.read_at is not None
        db.flush.assert_awaited()

    async def test_idempotent_keeps_original_read_at(self):
        original = datetime(2020, 1, 1, 12, 0, 0)
        message = Message(
            content="hi", sender_type="customer", channel_message_id="m1", read_at=original
        )
        db = self._db_returning(message)

        out = await mark_message_read(db, "m1")

        assert out.read_at == original  # unchanged on re-read

    async def test_not_found_returns_none(self):
        db = self._db_returning(None)
        # Not a UUID, so the primary-key fallback is skipped entirely.
        assert await mark_message_read(db, "not-a-uuid") is None


class TestWebsocketReadReceipt:
    def test_read_frame_sets_read_at_and_acks(self):
        message = Message(content="hi", sender_type="customer", channel_message_id="m1")
        query_result = MagicMock()
        query_result.scalar_one_or_none = MagicMock(return_value=message)
        db_session = MagicMock()
        db_session.execute = AsyncMock(return_value=query_result)
        db_session.flush = AsyncMock()
        db_session.commit = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_session)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("desk.channels.webchat.AsyncSessionLocal", return_value=cm):
            client = TestClient(app)
            with client.websocket_connect("/ws/chat/visitor-read") as websocket:
                connected = websocket.receive_json()
                assert connected["type"] == "connected"

                websocket.send_text(json.dumps({"type": "read", "message_id": "m1"}))
                ack = websocket.receive_json()

        assert ack["type"] == "read_ack"
        assert ack["message_id"] == "m1"
        assert ack["status"] == "read"
        assert ack["read_at"] is not None
        assert message.read_at is not None
        db_session.commit.assert_awaited()

    def test_read_frame_unknown_message_acks_not_found(self):
        query_result = MagicMock()
        query_result.scalar_one_or_none = MagicMock(return_value=None)
        db_session = MagicMock()
        db_session.execute = AsyncMock(return_value=query_result)
        db_session.flush = AsyncMock()
        db_session.commit = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_session)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("desk.channels.webchat.AsyncSessionLocal", return_value=cm):
            client = TestClient(app)
            with client.websocket_connect("/ws/chat/visitor-read-nf") as websocket:
                websocket.receive_json()  # connected
                websocket.send_text(json.dumps({"type": "read", "message_id": "ghost"}))
                ack = websocket.receive_json()

        assert ack["type"] == "read_ack"
        assert ack["status"] == "not_found"
        assert ack["read_at"] is None


class TestMediaFrameSize:
    def test_size_captured_when_present(self):
        raw = json.dumps(
            {"type": "file", "url": "https://cdn/d.pdf", "name": "d.pdf", "size": 2048}
        )
        media = parse_media_frame(raw)
        assert media["size"] == 2048

    def test_size_absent_when_not_supplied(self):
        raw = json.dumps({"type": "image", "url": "https://cdn/a.png", "name": "a.png"})
        media = parse_media_frame(raw)
        assert "size" not in media


class TestRouterMediaPersistence:
    """DC2 — rich-media metadata is persisted onto the message record."""

    def _router_with_mocks(self):
        router = MessageRouter(MagicMock(), MagicMock())
        router.event_bus.publish = AsyncMock()
        customer = MagicMock()
        customer.id = uuid.uuid4()
        conversation = MagicMock()
        conversation.id = uuid.uuid4()
        router.customer_resolver.resolve_or_create = AsyncMock(return_value=customer)
        router.conversation_manager.get_or_create_conversation = AsyncMock(
            return_value=conversation
        )
        router.conversation_manager.add_message = AsyncMock(return_value=MagicMock())
        return router

    async def test_media_metadata_persisted_and_readable(self):
        router = self._router_with_mocks()
        media = {
            "type": "image",
            "url": "https://cdn/a.png",
            "mime": "image/png",
            "name": "a.png",
            "size": 123,
        }
        inbound = InboundMessage(
            message_id="m1",
            conversation_id="visitor-1",
            channel="webchat",
            sender_identifier="visitor-1",
            sender_type="customer",
            content="caption",
            media_urls=["https://cdn/a.png"],
            metadata={"channel": "webchat", "media": media},
        )

        await router.route(inbound)

        kwargs = router.conversation_manager.add_message.await_args.kwargs
        persisted = kwargs["metadata"]
        assert persisted["media"] == media  # round-trips url/mime/name/size
        assert persisted["media_urls"] == ["https://cdn/a.png"]

    async def test_no_media_persists_no_media_key(self):
        router = self._router_with_mocks()
        inbound = InboundMessage(
            message_id="m2",
            conversation_id="visitor-1",
            channel="webchat",
            sender_identifier="visitor-1",
            sender_type="customer",
            content="plain text",
            media_urls=[],
            metadata={"channel": "webchat"},
        )

        await router.route(inbound)

        persisted = router.conversation_manager.add_message.await_args.kwargs["metadata"]
        assert "media" not in persisted
        assert persisted["channel"] == "webchat"
