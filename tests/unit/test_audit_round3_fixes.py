"""
Regression tests for full-audit round 1, batch 3 (.ocr-reports/full-audit.json).

Covers:
- #4  conversation history is PII-redacted on frontier-bound turns
- #6  outbound dispatch retries; processor dead-letters failed deliveries
- #8  XAUTOCLAIM pending-entry recovery + poison-entry claim cap
- #3  webchat session tokens required on the WS handshake
- #11 license feature gates enforce when LICENSE_ENFORCEMENT_ENABLED=true
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from desk.config import Settings
from desk.main import app


def _session_cm() -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock())
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestHistoryRedaction:
    """#4: raw prior customer turns must not reach frontier models."""

    def _engine(self, target):
        from desk.ai.engine import AIEngine

        engine = AIEngine.__new__(AIEngine)
        engine._refresh_runtime_config = AsyncMock()

        async def analyze(text: str):
            if "13812345678" in text:
                return SimpleNamespace(
                    pii_detected=True,
                    pii_types=["CN_PHONE"],
                    redacted_text="my number is [PHONE]",
                    routing_directive=SimpleNamespace(value="LOCAL_MODEL_ONLY"),
                )
            return SimpleNamespace(
                pii_detected=False,
                pii_types=[],
                redacted_text=text,
                routing_directive=SimpleNamespace(value="NO_RESTRICTION"),
            )

        engine.pii_shield = SimpleNamespace(analyze=AsyncMock(side_effect=analyze))
        engine.model_router = SimpleNamespace(
            route=AsyncMock(
                return_value=SimpleNamespace(target=target, model_name="m", fallback_chain=[])
            )
        )
        engine.vault_client = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
        engine.confidence_scorer = SimpleNamespace(
            score=AsyncMock(
                return_value=SimpleNamespace(
                    score=0.9, should_escalate=False, reasoning="ok", factors={}
                )
            )
        )
        llm_response = SimpleNamespace(
            text="answer", provider="p", model="m", tokens_used=1, metadata={}
        )
        engine.frontier_provider = SimpleNamespace(generate=AsyncMock(return_value=llm_response))
        engine.local_provider = SimpleNamespace(generate=AsyncMock(return_value=llm_response))
        engine._escalate_conversation = AsyncMock()
        return engine

    async def test_frontier_turn_redacts_customer_history(self) -> None:
        from desk.ai.model_router import ModelTarget

        engine = self._engine(ModelTarget.FRONTIER)
        policy = MagicMock()
        policy.run_pre_generation_hooks = AsyncMock(
            return_value={"policy_decision": "allow", "triggers": [], "redirect_response": None}
        )
        policy.run_post_generation_hooks = AsyncMock(
            return_value={"action": "allow", "violations": [], "append_texts": [], "is_valid": True}
        )
        builder = MagicMock()
        builder.build_prompt_with_persona = AsyncMock(return_value=("sys", "prompt"))
        history = [
            {"role": "customer", "content": "my number is 13812345678"},
            {"role": "agent", "content": "hello"},
        ]
        with (
            patch("desk.ai.engine.PolicyEngine", return_value=policy),
            patch("desk.ai.engine.AsyncSessionLocal", return_value=_session_cm()),
            patch(
                "desk.ai.engine.get_prompt_builder_with_persona",
                new=AsyncMock(return_value=builder),
            ),
        ):
            await engine.process_detailed(
                str(uuid4()), "how do I configure the api?", "webchat", "v1", history
            )

        sent_history = builder.build_prompt_with_persona.await_args.kwargs["conversation_history"]
        assert sent_history[0]["content"] == "my number is [PHONE]"
        assert sent_history[1]["content"] == "hello"  # non-customer turns untouched

    async def test_local_turn_keeps_history_unchanged(self) -> None:
        from desk.ai.model_router import ModelTarget

        engine = self._engine(ModelTarget.LOCAL)
        policy = MagicMock()
        policy.run_pre_generation_hooks = AsyncMock(
            return_value={"policy_decision": "allow", "triggers": [], "redirect_response": None}
        )
        policy.run_post_generation_hooks = AsyncMock(
            return_value={"action": "allow", "violations": [], "append_texts": [], "is_valid": True}
        )
        builder = MagicMock()
        builder.build_prompt_with_persona = AsyncMock(return_value=("sys", "prompt"))
        history = [{"role": "customer", "content": "my number is 13812345678"}]
        with (
            patch("desk.ai.engine.PolicyEngine", return_value=policy),
            patch("desk.ai.engine.AsyncSessionLocal", return_value=_session_cm()),
            patch(
                "desk.ai.engine.get_prompt_builder_with_persona",
                new=AsyncMock(return_value=builder),
            ),
        ):
            await engine.process_detailed(str(uuid4()), "help", "webchat", "v1", history)

        sent_history = builder.build_prompt_with_persona.await_args.kwargs["conversation_history"]
        assert sent_history[0]["content"] == "my number is 13812345678"
        # Only the current message was analyzed — no per-turn cost on local path.
        assert engine.pii_shield.analyze.await_count == 1


class TestOutboundRetry:
    """#6: transient send failures are retried; exhaustion returns failure."""

    def _dispatcher(self, send_mock):
        from desk.channels.outbound import OutboundDispatcher

        manager = MagicMock()
        adapter = MagicMock()
        adapter.config.channel_type = "whatsapp"
        adapter.send = send_mock
        manager.list_adapters.return_value = [adapter]
        return OutboundDispatcher(manager)

    async def test_retries_then_succeeds(self) -> None:
        from desk.schemas.channels import OutboundMessage

        send = AsyncMock(side_effect=[{"success": False, "error": "429"}, {"success": True}])
        dispatcher = self._dispatcher(send)
        msg = OutboundMessage(
            conversation_id="c", channel="whatsapp", recipient_identifier="+1", content="hi"
        )
        with patch("desk.channels.outbound.asyncio.sleep", new=AsyncMock()):
            result = await dispatcher.dispatch(msg)
        assert result["success"] is True
        assert send.await_count == 2

    async def test_exhausts_retries_and_reports_failure(self) -> None:
        from desk.schemas.channels import OutboundMessage

        send = AsyncMock(return_value={"success": False, "error": "500"})
        dispatcher = self._dispatcher(send)
        msg = OutboundMessage(
            conversation_id="c", channel="whatsapp", recipient_identifier="+1", content="hi"
        )
        with patch("desk.channels.outbound.asyncio.sleep", new=AsyncMock()):
            result = await dispatcher.dispatch(msg)
        assert result["success"] is False
        assert send.await_count == dispatcher.MAX_SEND_ATTEMPTS

    async def test_processor_dead_letters_failed_delivery(self, monkeypatch) -> None:
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())
        monkeypatch.setattr(processor, "_wait_for_visible_conversation", AsyncMock())
        monkeypatch.setattr(processor, "_conversation_ai_enabled", AsyncMock(return_value=True))
        monkeypatch.setattr(processor, "_load_history", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            processor.ai_engine,
            "process_detailed",
            AsyncMock(
                return_value=SimpleNamespace(
                    text="reply", model="m", routing="LOCAL", confidence=0.9,
                    escalated=False, blocked=False,
                )
            ),
        )
        monkeypatch.setattr(
            processor, "_persist_and_build_outbound", AsyncMock(return_value=MagicMock())
        )
        processor.outbound_dispatcher.dispatch = AsyncMock(
            return_value={"success": False, "error": "boom"}
        )
        processor.event_bus.dead_letter = AsyncMock()
        processor.event_bus.acknowledge = AsyncMock()

        await processor._process_message(
            {
                "event_id": "1-0",
                "payload": {
                    "conversation_id": str(uuid4()),
                    "content": "hi",
                    "channel": "whatsapp",
                    "sender_identifier": "+1",
                },
            }
        )
        processor.event_bus.dead_letter.assert_awaited_once()
        processor.event_bus.acknowledge.assert_awaited_once()


class TestPendingEntryRecovery:
    """#8: idle PEL entries are claimed and reprocessed; poison entries capped."""

    async def test_claim_pending_parses_entries(self) -> None:
        from desk.events.redis_streams import RedisStreamsEventBus

        client = MagicMock()
        client.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP already exists"))
        client.xautoclaim = AsyncMock(
            return_value=["0-0", [("1-0", {"payload": '{"x": 1}'})], []]
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        manager = MagicMock()
        manager.get_client.return_value = cm

        bus = RedisStreamsEventBus(manager)
        events = await bus.claim_pending("conversation.routed", "ai-processors", "processor-x")
        assert len(events) == 1
        assert events[0]["event_id"] == "1-0"
        assert events[0]["payload"] == {"x": 1}
        client.xautoclaim.assert_awaited_once()

    async def test_processor_processes_claimed_events(self, monkeypatch) -> None:
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())
        claimed = {"event_id": "2-0", "payload": {"conversation_id": "c"}}
        processor.event_bus.claim_pending = AsyncMock(return_value=[claimed])
        processor.event_bus.subscribe = AsyncMock(side_effect=asyncio.CancelledError())
        process = AsyncMock()
        monkeypatch.setattr(processor, "_process_message", process)

        await processor.run()
        process.assert_awaited_once_with(claimed)
        assert "2-0" not in processor._claim_counts

    async def test_poison_entry_dead_lettered_after_max_claims(self, monkeypatch) -> None:
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())
        processor._claim_counts["3-0"] = processor.MAX_CLAIM_ATTEMPTS
        processor.event_bus.claim_pending = AsyncMock(
            return_value=[{"event_id": "3-0", "payload": {"bad": True}}]
        )
        processor.event_bus.subscribe = AsyncMock(side_effect=asyncio.CancelledError())
        processor.event_bus.dead_letter = AsyncMock()
        processor.event_bus.acknowledge = AsyncMock()
        process = AsyncMock()
        monkeypatch.setattr(processor, "_process_message", process)

        await processor.run()
        processor.event_bus.dead_letter.assert_awaited_once()
        processor.event_bus.acknowledge.assert_awaited_once()
        process.assert_not_awaited()
        assert "3-0" not in processor._claim_counts


class TestWebchatSessionAuth:
    """#3: the visitor WS requires a server-issued, signed session token."""

    def test_session_endpoint_issues_verifiable_token(self) -> None:
        from desk.channels.webchat import _verify_visitor_token

        client = TestClient(app)
        res = client.post("/api/v1/webchat/session")
        assert res.status_code == 200
        body = res.json()
        assert body["visitor_id"].startswith("widget-")
        assert len(body["visitor_id"]) > len("widget-") + 10  # crypto-random, not 8 base36 chars
        assert _verify_visitor_token(body["visitor_id"], body["token"]) is True

    def test_ws_without_token_rejected(self) -> None:
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/chat/visitor-x"):
                pass
        assert exc.value.code == 4401

    def test_ws_token_bound_to_other_visitor_rejected(self) -> None:
        from desk.channels.webchat import _sign_visitor_token

        client = TestClient(app)
        token = _sign_visitor_token("someone-else", int(time.time()) + 3600)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/chat/visitor-x?token={token}"):
                pass
        assert exc.value.code == 4401

    def test_ws_expired_token_rejected(self) -> None:
        from desk.channels.webchat import _sign_visitor_token

        client = TestClient(app)
        token = _sign_visitor_token("visitor-x", int(time.time()) - 10)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/chat/visitor-x?token={token}"):
                pass
        assert exc.value.code == 4401

    def test_ws_valid_token_connects(self) -> None:
        from desk.channels.webchat import _sign_visitor_token

        client = TestClient(app)
        token = _sign_visitor_token("visitor-ok", int(time.time()) + 3600)
        with client.websocket_connect(f"/ws/chat/visitor-ok?token={token}") as ws:
            frame = ws.receive_json()
            assert frame["type"] == "connected"
            assert frame["visitor_id"] == "visitor-ok"


class TestLicenseFeatureGates:
    """#11: gates enforce when enabled; no-op by default."""

    async def test_disabled_by_default(self) -> None:
        from desk.license.gates import require_feature
        from desk.license.manager import FeatureGate

        settings = Settings(license_enforcement_enabled=False)
        with patch("desk.license.gates.get_settings", return_value=settings):
            assert await require_feature(FeatureGate.COMPLIANCE_TOOLS)() is None

    async def test_enabled_denies_free_tier(self) -> None:
        from desk.license.gates import require_feature
        from desk.license.manager import FeatureGate

        settings = Settings(license_enforcement_enabled=True)
        manager = MagicMock()
        manager.initialize = AsyncMock()
        manager.validate_license = AsyncMock(return_value=True)
        manager.check_feature_gate = MagicMock(return_value=False)
        with (
            patch("desk.license.gates.get_settings", return_value=settings),
            patch("desk.license.gates.AsyncSessionLocal", return_value=_session_cm()),
            patch("desk.license.gates.LicenseManager", return_value=manager),
        ):
            with pytest.raises(HTTPException) as exc:
                await require_feature(FeatureGate.COMPLIANCE_TOOLS)()
        assert exc.value.status_code == 402
        manager.validate_license.assert_awaited_once()

    async def test_enabled_allows_paid_tier(self) -> None:
        from desk.license.gates import require_feature
        from desk.license.manager import FeatureGate

        settings = Settings(license_enforcement_enabled=True)
        manager = MagicMock()
        manager.initialize = AsyncMock()
        manager.validate_license = AsyncMock(return_value=True)
        manager.check_feature_gate = MagicMock(return_value=True)
        with (
            patch("desk.license.gates.get_settings", return_value=settings),
            patch("desk.license.gates.AsyncSessionLocal", return_value=_session_cm()),
            patch("desk.license.gates.LicenseManager", return_value=manager),
        ):
            assert await require_feature(FeatureGate.CUSTOM_PERSONA)() is None
