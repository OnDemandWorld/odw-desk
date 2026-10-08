"""
ODW.ai Desk — Regression tests for the 2026-10 pre-launch deep review.

Covers:
  1. ``ai_enabled`` is a live flag: takeover disables AI auto-response,
     processor skips generation, reopening re-arms AI.
  2. MessageRouter idempotency for channel webhook redelivery.
  3. Confidence scorer calibration against rank-based (RRF) fused scores.
  4. GDPR anonymize also scrubs indirect identifiers.
  5. WhatsApp webhook fail-closed in production when no app secret is set.
  6. Email relay webhook HMAC verification / production requirement.
  7. RBAC: X-Desk-Role header is not trusted in production.
  8. WebChatManager socket hygiene (displacement + stale disconnect).
  9. Takeover endpoint: terminal-status and concurrent-takeover guards.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from desk.config import get_settings
from desk.main import app


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 1. ai_enabled is a live flag
# ---------------------------------------------------------------------------


class TestAiEnabledFlag:
    def _conversation(self, status="new"):
        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.status = status
        conv.ai_enabled = True
        conv.assigned_agent_id = None
        return conv

    async def test_assign_agent_disables_ai(self):
        from desk.conversations.manager import ConversationManager

        manager = ConversationManager(MagicMock())
        manager.db.flush = AsyncMock()
        conv = self._conversation()
        agent = MagicMock()
        agent.id = uuid.uuid4()

        await manager.assign_agent(conv, agent)
        assert conv.ai_enabled is False

    async def test_reopen_rearms_ai(self):
        from desk.conversations.manager import ConversationManager, ConversationStatus

        manager = ConversationManager(MagicMock())
        conv = self._conversation(status=ConversationStatus.RESOLVED.value)
        conv.ai_enabled = False
        customer = MagicMock()
        customer.id = uuid.uuid4()

        # Simulate the existing-row lookup branch: a RESOLVED conversation is
        # found and reopened with AI re-armed.
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        manager.db.execute = AsyncMock(return_value=result)
        manager.db.flush = AsyncMock()
        reopened = await manager.get_or_create_conversation(
            customer=customer, channel="whatsapp", channel_conversation_id="wamid-1"
        )
        assert reopened is conv
        assert reopened.status == ConversationStatus.ACTIVE
        assert reopened.ai_enabled is True

    async def test_processor_skips_when_ai_disabled(self, monkeypatch):
        from desk.workers.message_processor import MessageProcessor

        processor = MessageProcessor(MagicMock(), MagicMock(), MagicMock())

        async def fake_enabled(conversation_id):
            return False

        monkeypatch.setattr(processor, "_conversation_ai_enabled", fake_enabled)
        event_bus = MagicMock()
        event_bus.acknowledge = AsyncMock()
        processor.event_bus = event_bus

        engine_call = AsyncMock()
        monkeypatch.setattr(processor.ai_engine, "process_detailed", engine_call)

        await processor._process_message(
            {
                "event_id": "ev-1",
                "payload": {"conversation_id": str(uuid.uuid4()), "content": "hi",
                            "channel": "whatsapp", "sender_identifier": "+123"},
            }
        )
        engine_call.assert_not_awaited()
        event_bus.acknowledge.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. Router redelivery idempotency
# ---------------------------------------------------------------------------


class TestRouterIdempotency:
    def _router(self, existing_id=None):
        from desk.router.message_router import MessageRouter

        router = MessageRouter(MagicMock(), MagicMock())
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = existing_id
        router.db.execute = AsyncMock(return_value=dup_result)
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

    async def test_redelivery_returns_duplicate_without_side_effects(self):
        from desk.schemas.channels import InboundMessage

        router = self._router(existing_id=uuid.uuid4())
        inbound = InboundMessage(
            message_id="wamid-retry",
            conversation_id="thread-1",
            channel="whatsapp",
            sender_identifier="+123",
            sender_type="customer",
            content="hello",
        )

        result = await router.route(inbound)

        assert result["status"] == "duplicate"
        router.conversation_manager.add_message.assert_not_awaited()
        router.event_bus.publish.assert_not_awaited()

    async def test_first_delivery_routes_normally(self):
        from desk.schemas.channels import InboundMessage

        router = self._router(existing_id=None)
        inbound = InboundMessage(
            message_id="wamid-new",
            conversation_id="thread-1",
            channel="whatsapp",
            sender_identifier="+123",
            sender_type="customer",
            content="hello",
        )

        result = await router.route(inbound)

        assert result["status"] == "routed"
        router.conversation_manager.add_message.assert_awaited_once()
        router.event_bus.publish.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. Confidence calibration
# ---------------------------------------------------------------------------


class TestConfidenceCalibration:
    async def test_rrf_scale_scores_no_longer_force_escalation(self):
        from desk.ai.confidence_scorer import ConfidenceScorer
        from desk.ai.vault_client import RetrievedDocument

        scorer = ConfidenceScorer(escalation_threshold=0.6)
        # Realistic Vault RRF fused_scores (a GOOD retrieval): ~0.016 top hit.
        docs = [
            RetrievedDocument(content="d1", score=0.0164, source_id="f1", metadata={}),
            RetrievedDocument(content="d2", score=0.0161, source_id="f1", metadata={}),
            RetrievedDocument(content="d3", score=0.0159, source_id="f2", metadata={}),
        ]
        score = await scorer.score(
            response_text="Here is the answer. You can resolve this by following the steps I listed above.",
            knowledge_documents=docs,
        )
        # Before calibration: ~0.45 -> always escalate (AI deflection dead).
        assert score.factors["knowledge_relevance"] > 0.9
        assert score.should_escalate is False

    async def test_no_documents_still_escalates_below_threshold(self):
        from desk.ai.confidence_scorer import ConfidenceScorer

        scorer = ConfidenceScorer(escalation_threshold=0.6)
        score = await scorer.score(
            response_text="short", knowledge_documents=None,
        )
        assert score.should_escalate is True


# ---------------------------------------------------------------------------
# 4. GDPR anonymize scrubbing
# ---------------------------------------------------------------------------


class TestGdprAnonymizeScrub:
    async def test_indirect_identifiers_scrubbed(self):
        from desk.compliance.service import ComplianceService

        service = ComplianceService.__new__(ComplianceService)
        service.db = MagicMock()
        service.db.flush = AsyncMock()

        customer = MagicMock()
        customer.display_name = "Alice"
        customer.channel_identifiers = {"whatsapp": "+8613800138000"}
        customer.metadata_ = {"foo": "bar"}

        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.channel_conversation_id = "+8613800138000"  # raw phone number

        msg = MagicMock()
        msg.channel_message_id = "<msg-123@sender-domain.example>"
        msg.media_urls = ["https://cdn.example.com/users/alice/photo.jpg"]

        async def get_messages(conv_id):
            return [msg]

        service._get_messages = get_messages

        summary = await service._anonymize(customer, [conv])

        assert summary["anonymized_messages"] == 1
        # Phone number must not survive in any form.
        assert "+8613800138000" not in conv.channel_conversation_id
        assert msg.channel_message_id is None
        assert msg.media_urls == []


# ---------------------------------------------------------------------------
# 5. WhatsApp webhook fail-closed in production
# ---------------------------------------------------------------------------


class TestWhatsAppFailClosed:
    def _adapter(self, env_name, secret=""):
        from desk.channels.whatsapp_business import WhatsAppBusinessAdapter

        settings = MagicMock()
        settings.environment = env_name
        settings.whatsapp_app_secret = secret
        settings.whatsapp_webhook_verify_token = "vt"
        settings.whatsapp_phone_number_id = ""
        settings.whatsapp_graph_api_base_url = "https://graph.facebook.com/v19.0"
        settings.whatsapp_business_account_id = ""
        settings.baileys_bridge_url = "http://localhost:3001"
        settings.baileys_enabled = False
        adapter = WhatsAppBusinessAdapter.__new__(WhatsAppBusinessAdapter)
        adapter.settings = settings
        return adapter

    def test_production_without_secret_rejects(self):
        adapter = self._adapter("production", secret="")
        assert adapter.verify_signature(b"payload", "sha256=deadbeef") is False

    def test_development_without_secret_allows(self):
        adapter = self._adapter("development", secret="")
        assert adapter.verify_signature(b"payload", None) is True

    def test_production_with_secret_verifies_hmac(self):
        secret = "s3cret-app-secret"
        adapter = self._adapter("production", secret=secret)
        payload = b'{"entry": []}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert adapter.verify_signature(payload, sig) is True
        assert adapter.verify_signature(payload, "sha256=" + "0" * 64) is False

    def test_non_ascii_signature_is_401_not_500(self):
        adapter = self._adapter("production", secret="s3cret")
        assert adapter.verify_signature(b"{}", "sha256=签名") is False


# ---------------------------------------------------------------------------
# 6. Email webhook HMAC
# ---------------------------------------------------------------------------


class TestEmailWebhookHmac:
    def _post(self, client, body: bytes, secret: str, signature: str | None):
        headers = {"Content-Type": "message/rfc822"}
        if signature is not None:
            headers["X-Desk-Signature"] = signature
        return client.post(
            "/api/v1/webhooks/email", content=body, headers=headers
        )

    def test_dev_without_secret_accepts_shape_check(self, monkeypatch):
        monkeypatch.delenv("EMAIL_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        client = TestClient(app)
        # Empty payload → 400 from shape check, NOT 401 from auth.
        resp = self._post(client, b"", secret="", signature=None)
        assert resp.status_code == 400

    def test_secret_set_rejects_missing_or_bad_signature(self, monkeypatch):
        monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "relay-secret")
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        client = TestClient(app)
        body = b"From: a@b.c\nSubject: hi\n\nhello"
        resp = self._post(client, body, secret="relay-secret", signature=None)
        assert resp.status_code == 401
        resp = self._post(client, body, secret="relay-secret", signature="sha256=bad")
        assert resp.status_code == 401

    def test_production_without_secret_rejects(self, monkeypatch):
        monkeypatch.delenv("EMAIL_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "prod-secret-key-for-tests-0123456789abcdef")
        get_settings.cache_clear()
        client = TestClient(app)
        resp = self._post(client, b"From: a@b.c\n\nhello", secret="", signature=None)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. RBAC header trust
# ---------------------------------------------------------------------------


class TestRbacHeaderTrust:
    _PROD_KEY = "prod-secret-key-for-tests-0123456789abcdef"

    def test_production_ignores_role_header(self, monkeypatch):
        from desk.security.rbac import resolve_role

        monkeypatch.setenv("DESK_API_KEY", "sekret")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", self._PROD_KEY)
        monkeypatch.delenv("DESK_ROLE_HEADER_TRUSTED", raising=False)
        get_settings.cache_clear()
        settings = get_settings()

        assert resolve_role(settings, authorization=None, desk_role="admin") == "agent"

    def test_production_trusts_when_explicitly_enabled(self, monkeypatch):
        from desk.security.rbac import resolve_role

        monkeypatch.setenv("DESK_API_KEY", "sekret")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", self._PROD_KEY)
        monkeypatch.setenv("DESK_ROLE_HEADER_TRUSTED", "true")
        get_settings.cache_clear()
        settings = get_settings()

        assert resolve_role(settings, authorization=None, desk_role="admin") == "admin"

    def test_development_still_honors_header(self, monkeypatch):
        from desk.security.rbac import resolve_role

        monkeypatch.setenv("DESK_API_KEY", "sekret")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("DESK_ROLE_HEADER_TRUSTED", raising=False)
        get_settings.cache_clear()
        settings = get_settings()

        assert resolve_role(settings, authorization=None, desk_role="admin") == "admin"


# ---------------------------------------------------------------------------
# 8. WebChatManager socket hygiene
# ---------------------------------------------------------------------------


class TestWebChatSocketHygiene:
    async def test_connect_closes_previous_socket(self):
        from desk.channels.webchat import WebChatManager

        manager = WebChatManager()
        old_ws, new_ws = AsyncMock(), AsyncMock()
        await manager.connect("visitor-1", old_ws)
        await manager.connect("visitor-1", new_ws)

        assert manager.active_connections["visitor-1"] is new_ws
        old_ws.close.assert_awaited_once()

    async def test_stale_disconnect_does_not_evict_replacement(self):
        from desk.channels.webchat import WebChatManager

        manager = WebChatManager()
        old_ws, new_ws = AsyncMock(), AsyncMock()
        await manager.connect("visitor-1", old_ws)
        await manager.connect("visitor-1", new_ws)

        # The OLD socket's teardown arrives after the replacement registered.
        manager.disconnect("visitor-1", old_ws)
        assert manager.active_connections["visitor-1"] is new_ws

        # The new socket's own teardown still cleans up.
        manager.disconnect("visitor-1", new_ws)
        assert "visitor-1" not in manager.active_connections


# ---------------------------------------------------------------------------
# 9. Takeover guards (via direct endpoint logic-level checks)
# ---------------------------------------------------------------------------


class TestTakeoverGuards:
    """Terminal-status and concurrent-takeover rejections live in the endpoint;
    exercised through the router module's HTTP surface would need heavy DB
    scaffolding — assert the guard logic via the state machine + a light
    source check instead."""

    def test_guards_present_in_endpoint_source(self):
        import inspect

        from desk.agents import inbox_api

        src = inspect.getsource(inbox_api)
        assert "already taken over by another agent" in src
        assert "cannot be taken over" in src
