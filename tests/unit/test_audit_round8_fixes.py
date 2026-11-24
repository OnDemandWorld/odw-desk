"""
Regression tests for full-audit round 1, batch 8 (.ocr-reports/full-audit.json).

Covers worker & event-pipeline durability:
- #42 event acked only after a successful dead-letter write
- #43 invisible conversation leaves the event pending (no inference, no ack)
- #44 engine cache keyed by loop object, not id(loop)
- #45 XADD carries bounded MAXLEN retention
- #46 SLA scanner runs only under the Redis distributed lock
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from desk.events.redis_streams import DLQ_MAXLEN, STREAM_MAXLEN


def _payload() -> dict:
    return {
        "event_id": "1-0",
        "payload": {
            "conversation_id": str(uuid4()),
            "content": "hi",
            "channel": "whatsapp",
            "sender_identifier": "+1",
        },
    }


class TestDlqBeforeAck:
    """#42: a failed DLQ write must leave the event pending."""

    async def test_no_ack_when_dead_letter_fails(self, monkeypatch) -> None:
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())
        monkeypatch.setattr(
            processor, "_wait_for_visible_conversation", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(
            processor, "_conversation_ai_enabled", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(processor, "_load_history", AsyncMock(return_value=[]))
        processor.ai_engine.process_detailed = AsyncMock(side_effect=RuntimeError("boom"))
        processor.event_bus.dead_letter = AsyncMock(side_effect=RuntimeError("redis OOM"))
        processor.event_bus.acknowledge = AsyncMock()

        await processor._process_message(_payload())
        processor.event_bus.dead_letter.assert_awaited_once()
        processor.event_bus.acknowledge.assert_not_awaited()

    async def test_ack_after_successful_dead_letter(self, monkeypatch) -> None:
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())
        monkeypatch.setattr(
            processor, "_wait_for_visible_conversation", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(
            processor, "_conversation_ai_enabled", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(processor, "_load_history", AsyncMock(return_value=[]))
        processor.ai_engine.process_detailed = AsyncMock(side_effect=RuntimeError("boom"))
        processor.event_bus.dead_letter = AsyncMock()
        processor.event_bus.acknowledge = AsyncMock()

        await processor._process_message(_payload())
        processor.event_bus.acknowledge.assert_awaited_once()


class TestInvisibleConversationPending:
    """#43: prolonged invisibility must not run inference or ack."""

    async def test_invisible_leaves_pending(self, monkeypatch) -> None:
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())
        monkeypatch.setattr(
            processor, "_wait_for_visible_conversation", AsyncMock(return_value=False)
        )
        processor.ai_engine.process_detailed = AsyncMock()
        processor.event_bus.acknowledge = AsyncMock()
        processor.event_bus.dead_letter = AsyncMock()

        await processor._process_message(_payload())
        processor.ai_engine.process_detailed.assert_not_awaited()
        processor.event_bus.acknowledge.assert_not_awaited()
        processor.event_bus.dead_letter.assert_not_awaited()


class TestEngineCacheLoopIdentity:
    """#44: engines are cached per loop object, never reused across loops."""

    def test_same_loop_same_engine(self) -> None:
        from desk.db import get_engine

        async def two_calls():
            return get_engine() is get_engine()

        assert asyncio.run(two_calls()) is True

    def test_different_loops_different_engines(self) -> None:
        from desk.db import get_engine

        async def one():
            return get_engine()

        e1 = asyncio.run(one())
        e2 = asyncio.run(one())
        assert e1 is not e2


class TestStreamRetention:
    """#45: XADD must carry approximate MAXLEN bounds."""

    async def test_publish_maxlen(self) -> None:
        from desk.events.redis_streams import RedisStreamsEventBus

        client = MagicMock()
        client.xadd = AsyncMock(return_value="1-0")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        manager = MagicMock()
        manager.get_client.return_value = cm

        bus = RedisStreamsEventBus(manager)
        await bus.publish("conversation.routed", {"x": 1})
        kwargs = client.xadd.await_args.kwargs
        assert kwargs["maxlen"] == STREAM_MAXLEN
        assert kwargs["approximate"] is True

    async def test_dead_letter_maxlen(self) -> None:
        from desk.events.redis_streams import RedisStreamsEventBus

        client = MagicMock()
        client.xadd = AsyncMock(return_value="1-0")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        manager = MagicMock()
        manager.get_client.return_value = cm

        bus = RedisStreamsEventBus(manager)
        await bus.dead_letter("conversation.routed", {"x": 1}, "test")
        kwargs = client.xadd.await_args.kwargs
        assert kwargs["maxlen"] == DLQ_MAXLEN


class TestSlaScannerLock:
    """#46: the scan runs only when the distributed lock is acquired."""

    def _lifespan_patches(self, lock_acquired: bool):
        import desk.main as main_mod

        redis_client = MagicMock()
        redis_client.set = AsyncMock(return_value=lock_acquired)
        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(return_value=redis_client)
        client_cm.__aexit__ = AsyncMock(return_value=False)
        redis_manager = MagicMock()
        redis_manager.connect = AsyncMock()
        redis_manager.disconnect = AsyncMock()
        redis_manager.get_client.return_value = client_cm
        event_bus = MagicMock()
        event_bus.connect = AsyncMock()
        event_bus.disconnect = AsyncMock()
        channel_manager = MagicMock()
        channel_manager.start_all = AsyncMock()
        channel_manager.stop_all = AsyncMock()
        processor = MagicMock()
        processor.run = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_cm.__aexit__ = AsyncMock(return_value=False)
        license_manager = MagicMock()
        license_manager.initialize = AsyncMock()
        engine = MagicMock()
        engine.dispose = AsyncMock()
        scan = AsyncMock(return_value={})
        patches = [
            patch.object(main_mod, "get_redis_manager", return_value=redis_manager),
            patch.object(main_mod, "RedisStreamsEventBus", return_value=event_bus),
            patch.object(main_mod, "ChannelAdapterManager", return_value=channel_manager),
            patch.object(main_mod, "get_whatsapp_adapter", return_value=None),
            patch.object(main_mod, "WebChatAdapter", return_value=MagicMock()),
            patch.object(main_mod, "EmailChannelAdapter", return_value=MagicMock()),
            patch.object(main_mod, "MessageProcessor", return_value=processor),
            patch.object(main_mod, "AIEngine", return_value=MagicMock()),
            patch.object(main_mod, "AsyncSessionLocal", return_value=session_cm),
            patch.object(main_mod, "scan_due_conversations", new=scan),
            patch.object(main_mod, "get_engine", return_value=engine),
            patch("desk.license.manager.LicenseManager", return_value=license_manager),
            patch("desk.admin.runtime_settings.load_all", new=AsyncMock(return_value={})),
        ]
        return patches, scan

    def test_scan_skipped_without_lock(self) -> None:
        from fastapi.testclient import TestClient

        from desk.main import app

        patches, scan = self._lifespan_patches(lock_acquired=False)
        for p in patches:
            p.start()
        try:
            with TestClient(app):
                import time

                time.sleep(0.1)  # let the scanner task run its first iteration
        finally:
            for p in patches:
                p.stop()
        scan.assert_not_awaited()

    def test_scan_runs_with_lock(self) -> None:
        from fastapi.testclient import TestClient

        from desk.main import app

        patches, scan = self._lifespan_patches(lock_acquired=True)
        for p in patches:
            p.start()
        try:
            with TestClient(app):
                import time

                time.sleep(0.1)  # let the scanner task run its first iteration
        finally:
            for p in patches:
                p.stop()
        scan.assert_awaited()
