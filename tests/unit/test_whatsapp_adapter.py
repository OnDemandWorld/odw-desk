"""
ODW.ai Desk — Unit Tests for WhatsApp Business API Adapter

Tests webhook verification and inbound message parsing.
"""

import pytest
from fastapi.testclient import TestClient

from desk.channels.whatsapp_business import AdapterConfig, WhatsAppBusinessAdapter
from desk.main import app


@pytest.fixture
def client():
    """Return FastAPI test client."""
    return TestClient(app)


class TestWhatsAppBusinessAdapter:
    """Tests for WhatsAppBusinessAdapter."""

    @pytest.fixture
    def adapter(self):
        """Return adapter instance."""
        config = AdapterConfig(
            adapter_id="whatsapp-business-test",
            adapter_name="WhatsApp Business API Test",
            channel_type="whatsapp_business",
        )
        return WhatsAppBusinessAdapter(config)

    def test_parse_text_message(self, adapter):
        """Test parsing a text message from Meta webhook payload."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "12345"},
                                "messages": [
                                    {
                                        "id": "wamid.abc123",
                                        "from": "+5511999887766",
                                        "type": "text",
                                        "text": {"body": "Hello, I need help"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        messages = adapter.parse_inbound_message(payload)

        assert len(messages) == 1
        assert messages[0].message_id == "wamid.abc123"
        assert messages[0].channel == "whatsapp"
        assert messages[0].sender_identifier == "+5511999887766"
        assert messages[0].content == "Hello, I need help"

    def test_parse_no_messages(self, adapter):
        """Test parsing payload with no messages."""
        payload = {"entry": []}
        messages = adapter.parse_inbound_message(payload)
        assert len(messages) == 0

    def test_parse_extracts_contact_profile_name(self, adapter):
        """Contact profile name is carried as sender_name (Chatwoot-style)."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "12345"},
                                "contacts": [
                                    {"profile": {"name": "Alice Smoke"}, "wa_id": "+15559876501"}
                                ],
                                "messages": [
                                    {
                                        "id": "wamid.name1",
                                        "from": "+15559876501",
                                        "type": "text",
                                        "text": {"body": "Hi"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        messages = adapter.parse_inbound_message(payload)
        assert messages[0].sender_name == "Alice Smoke"

        # Without a contacts block the name stays None.
        del payload["entry"][0]["changes"][0]["value"]["contacts"]
        messages = adapter.parse_inbound_message(payload)
        assert messages[0].sender_name is None


class TestWhatsAppWebhookEndpoints:
    """Tests for FastAPI webhook endpoints."""

    def test_webhook_verification(self, client):
        """Test GET /api/v1/webhooks/whatsapp verification."""
        response = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "dev_verify_token",
                "hub.challenge": "1234567890",
            },
        )
        assert response.status_code == 200
        # Meta requires the raw challenge echoed back as plain text
        # (JSON-quoting it fails webhook verification).
        assert response.text == "1234567890"
        assert response.headers["content-type"].startswith("text/plain")

    def test_webhook_verification_invalid_token(self, client):
        """Test verification with invalid token."""
        response = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "invalid_token",
                "hub.challenge": "1234567890",
            },
        )
        assert response.status_code == 403
