"""
ODW.ai Desk — Unit Tests for WhatsApp Webhook HMAC Verification

Meta signs the raw body with the WhatsApp *app secret* and sends
``X-Hub-Signature-256: sha256=<hex>``. These tests cover:
- valid signature accepted
- invalid / missing signature rejected (when a secret is configured)
- missing app secret -> verification skipped (dev convenience)
"""

import hashlib
import hmac

import pytest

from desk.channels.base import AdapterConfig
from desk.channels.whatsapp_business import WhatsAppBusinessAdapter
from desk.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _adapter() -> WhatsAppBusinessAdapter:
    config = AdapterConfig(
        adapter_id="wa-hmac-test",
        adapter_name="WhatsApp HMAC Test",
        channel_type="whatsapp_business",
    )
    return WhatsAppBusinessAdapter(config)


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestWebhookHMAC:
    """Tests for WhatsAppBusinessAdapter.verify_signature()."""

    def test_valid_signature_accepted(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "top-secret")
        get_settings.cache_clear()
        adapter = _adapter()
        body = b'{"entry": []}'

        assert adapter.verify_signature(body, _signature("top-secret", body)) is True

    def test_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "top-secret")
        get_settings.cache_clear()
        adapter = _adapter()
        body = b'{"entry": []}'

        assert adapter.verify_signature(body, "sha256=deadbeef") is False
        # Signed with a different secret -> rejected.
        assert adapter.verify_signature(body, _signature("wrong-secret", body)) is False

    def test_missing_signature_rejected_when_secret_configured(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "top-secret")
        get_settings.cache_clear()
        adapter = _adapter()

        assert adapter.verify_signature(b"{}", None) is False

    def test_missing_app_secret_skips_verification(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "")
        get_settings.cache_clear()
        adapter = _adapter()

        # No secret configured -> skip verification (dev), accept anything.
        assert adapter.verify_signature(b"{}", None) is True
        assert adapter.verify_signature(b"{}", "sha256=anything") is True
