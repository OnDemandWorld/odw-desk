"""
ODW.ai Desk — End-to-End Test Suite (DEPLOY-003)

Comprehensive E2E tests for the complete message pipeline.
"""

import asyncio
import time
from uuid import uuid4

import httpx
import pytest


@pytest.mark.e2e
class TestEndToEndMessageFlow:
    """End-to-end tests for the complete message flow."""

    @pytest.fixture
    async def client(self):
        """Create async HTTP client."""
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            yield client

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "version" in data

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_verification(self, client):
        """Test WhatsApp webhook verification."""
        verify_token = "dev_verify_token"
        challenge = "test_challenge_123"

        response = await client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": verify_token,
                "hub.challenge": challenge,
            },
        )

        assert response.status_code == 200
        assert response.text == challenge

    @pytest.mark.asyncio
    async def test_complete_message_pipeline(self, client):
        """Test complete message flow from WhatsApp to AI response."""
        # Generate unique message ID
        message_id = f"wamid.test.{uuid4()}"
        phone_number = "+1234567890"
        message_text = "Hello, I need help with my appointment"

        # Send WhatsApp webhook
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "BUSINESS_ACCOUNT_ID",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": phone_number,
                                    "phone_number_id": "PHONE_NUMBER_ID",
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Test User"},
                                        "wa_id": phone_number,
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": phone_number,
                                        "id": message_id,
                                        "timestamp": str(int(time.time())),
                                        "type": "text",
                                        "text": {"body": message_text},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

        # Calculate HMAC signature
        import hashlib
        import hmac

        secret = "dev_secret_key_change_me"
        payload_bytes = str(payload).encode()
        signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

        response = await client.post(
            "/api/v1/webhooks/whatsapp",
            json=payload,
            headers={"X-Hub-Signature-256": f"sha256={signature}"},
        )

        assert response.status_code == 200

        # Wait for async processing
        await asyncio.sleep(2)

        # Verify conversation was created (would need DB access or API endpoint)
        # This is a simplified E2E test - full implementation would verify
        # database state and outbound message dispatch

    @pytest.mark.asyncio
    async def test_agent_inbox_list_conversations(self, client):
        """Test agent inbox conversation listing."""
        response = await client.get("/api/v1/agents/conversations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_admin_setup_status(self, client):
        """Test admin setup status endpoint."""
        response = await client.get("/api/v1/admin/setup/status")
        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert "setup_complete" in data

    @pytest.mark.asyncio
    async def test_persona_list(self, client):
        """Test persona listing endpoint."""
        response = await client.get("/api/v1/admin/personas")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_policy_list(self, client):
        """Test policy listing endpoint."""
        response = await client.get("/api/v1/admin/policies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.e2e
class TestAIIntelligencePipeline:
    """E2E tests for AI intelligence pipeline components."""

    @pytest.mark.asyncio
    async def test_pii_shield_detection(self):
        """Test PII detection and redaction."""
        from desk.ai.pii_shield import PIIShield

        shield = PIIShield()

        # Test with PII
        text_with_pii = "My name is John Doe and my phone is 555-1234"
        result = await shield.analyze(text_with_pii)

        assert result.pii_detected is True
        assert len(result.pii_types) > 0
        assert result.redacted_text != text_with_pii

        # Test without PII
        text_without_pii = "Hello, how are you?"
        result = await shield.analyze(text_without_pii)

        assert result.pii_detected is False
        assert result.redacted_text == text_without_pii

    @pytest.mark.asyncio
    async def test_model_routing(self):
        """Test model routing decisions."""
        from desk.ai.model_router import ModelRouter
        from desk.ai.pii_shield import RoutingDirective

        router = ModelRouter(
            local_model_endpoint="http://localhost:11434",
            local_model_name="llama-3.1-8b",
            frontier_model_endpoint="https://api.openai.com/v1",
            frontier_model_name="gpt-4o-mini",
            frontier_enabled=True,
        )

        # Test no PII, low complexity
        decision = await router.route(
            pii_directive=RoutingDirective.NO_RESTRICTION,
            text="Hello",
            context_depth=0,
        )
        assert decision.target.value in ["local", "frontier"]

        # Test PII detected
        decision = await router.route(
            pii_directive=RoutingDirective.LOCAL_MODEL_ONLY,
            text="My SSN is 123-45-6789",
            context_depth=0,
        )
        assert decision.target.value == "local"

    @pytest.mark.asyncio
    async def test_confidence_scoring(self):
        """Test confidence scoring."""
        from desk.ai.confidence_scorer import ConfidenceScorer

        scorer = ConfidenceScorer(escalation_threshold=0.5)

        # Test good response
        score = await scorer.score(
            response_text="I can help you with that. Here's the solution...",
            knowledge_documents=None,
        )
        assert 0.0 <= score.score <= 1.0

        # Test poor response
        score = await scorer.score(
            response_text="I don't know",
            knowledge_documents=None,
        )
        assert score.score < 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
