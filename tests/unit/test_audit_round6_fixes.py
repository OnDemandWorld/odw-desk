"""
Regression tests for full-audit round 1, batch 6 (.ocr-reports/full-audit.json).

Covers channel verification & delivery hardening:
- #20 WhatsApp webhook fails open no more when outbound credentials are live
- #21 SMTP STARTTLS verifies the server certificate
- #22 email webhook HMAC verified over the exact received body bytes
- #23 outbound email never stubs success while inbound mail is accepted
- #24 SMTP connections carry an explicit socket timeout
"""

import hashlib
import hmac
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from desk.config import Settings
from desk.dependencies import get_db
from desk.main import app


def _wa_adapter():
    from desk.channels.base import AdapterConfig
    from desk.channels.whatsapp_business import WhatsAppBusinessAdapter

    return WhatsAppBusinessAdapter(
        AdapterConfig(
            adapter_id="wa-t",
            adapter_name="WA",
            channel_type="whatsapp_business",
            enabled=True,
        )
    )


class TestWhatsAppFailClosed:
    """#20: no app secret + live outbound credentials must reject webhooks."""

    def test_live_credentials_fail_closed_in_development(self) -> None:
        adapter = _wa_adapter()
        settings = Settings(environment="development", whatsapp_app_secret="")
        with (
            patch("desk.channels.whatsapp_business.get_settings", return_value=settings),
            patch(
                "desk.admin.runtime_settings.get_override",
                return_value={"access_token": "live-token"},
            ),
        ):
            assert adapter.verify_signature(b"{}", None) is False

    def test_no_credentials_dev_still_skips(self) -> None:
        adapter = _wa_adapter()
        settings = Settings(environment="development", whatsapp_app_secret="")
        with (
            patch("desk.channels.whatsapp_business.get_settings", return_value=settings),
            patch("desk.admin.runtime_settings.get_override", return_value=None),
        ):
            assert adapter.verify_signature(b"{}", None) is True


class TestSmtpTlsVerification:
    """#21: STARTTLS must use a certificate-verifying context."""

    def test_starttls_uses_verifying_context(self) -> None:
        from desk.channels.email import EmailChannel

        smtp = MagicMock()
        settings = Settings(
            email_enabled=True,
            email_smtp_host="smtp.test",
            email_use_tls=True,
            email_smtp_user="u",
            email_smtp_password="p",
        )
        channel = EmailChannel(settings=settings, smtp_factory=lambda h, p: smtp)
        result = channel.send_reply("to@example.com", "subj", "body")
        assert result["success"] is True
        smtp.starttls.assert_called_once()
        ctx = smtp.starttls.call_args.kwargs["context"]
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED


class TestEmailWebhookHmac:
    """#22: HMAC must cover the full received body, including JSON envelopes."""

    def _client(self, secret: str) -> TestClient:
        from desk.channels.email import router as email_router  # noqa: F401

        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_json_envelope_signed_over_full_body_accepted(self) -> None:
        secret = "s3cret"
        body = json.dumps({"raw": "From: a@b.com\r\nSubject: hi\r\n\r\nhello"}).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        settings = Settings(email_webhook_secret=secret)
        channel = MagicMock()
        channel.route_inbound = AsyncMock(return_value={"status": "routed"})
        with (
            patch("desk.channels.email.get_settings", return_value=settings),
            patch("desk.channels.email.get_email_channel", return_value=channel),
            patch("desk.channels.email.get_event_bus", return_value=MagicMock()),
        ):
            client = self._client(secret)
            res = client.post(
                "/api/v1/webhooks/email",
                content=body,
                headers={"content-type": "application/json", "x-desk-signature": sig},
            )
        app.dependency_overrides.clear()
        assert res.status_code == 200

    def test_json_envelope_signed_over_raw_only_rejected(self) -> None:
        secret = "s3cret"
        raw = "From: a@b.com\r\nSubject: hi\r\n\r\nhello"
        body = json.dumps({"raw": raw}).encode()
        # The OLD (buggy) verification computed the HMAC over the raw field.
        sig = "sha256=" + hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        settings = Settings(email_webhook_secret=secret)
        with patch("desk.channels.email.get_settings", return_value=settings):
            client = self._client(secret)
            res = client.post(
                "/api/v1/webhooks/email",
                content=body,
                headers={"content-type": "application/json", "x-desk-signature": sig},
            )
        app.dependency_overrides.clear()
        assert res.status_code == 401


class TestEmailNoSilentStub:
    """#23: production / inbound-enabled deployments must not stub success."""

    def test_production_unconfigured_smtp_fails(self) -> None:
        from desk.channels.email import EmailChannel

        settings = Settings(
            environment="production", secret_key="a" * 64, email_enabled=False
        )
        channel = EmailChannel(settings=settings)
        result = channel.send_reply("to@example.com", "subj", "body")
        assert result["success"] is False

    def test_inbound_secret_configured_smtp_missing_fails(self) -> None:
        from desk.channels.email import EmailChannel

        settings = Settings(email_webhook_secret="s", email_enabled=False)
        channel = EmailChannel(settings=settings)
        result = channel.send_reply("to@example.com", "subj", "body")
        assert result["success"] is False

    def test_dev_unconfigured_still_stubs(self) -> None:
        from desk.channels.email import EmailChannel

        channel = EmailChannel(settings=Settings(email_enabled=False))
        result = channel.send_reply("to@example.com", "subj", "body")
        assert result["success"] is True
        assert result["stubbed"] is True


class TestSmtpTimeout:
    """#24: stdlib SMTP connections must carry an explicit timeout."""

    def test_open_smtp_passes_timeout(self) -> None:
        from desk.channels.email import SMTP_TIMEOUT_SECONDS, EmailChannel

        channel = EmailChannel(settings=Settings())
        with patch("desk.channels.email.smtplib.SMTP") as smtp_cls:
            channel._open_smtp("smtp.test", 587)
        assert smtp_cls.call_args.kwargs["timeout"] == SMTP_TIMEOUT_SECONDS
