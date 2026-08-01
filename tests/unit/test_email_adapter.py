"""
ODW.ai Desk — Unit Tests for the Email Channel Adapter (V1.5 F-2, EM1-EM3)

Inbound: a raw RFC822 message is parsed (pure function) and normalized to a
canonical InboundMessage (channel="email") handed to the shared MessageRouter
(mocked here), with thread reuse via In-Reply-To/References or sender+subject.
Outbound: send_reply delivers over an injectable SMTP transport; when SMTP is
not configured it is gracefully stubbed (dev).
"""

from email import message_from_string, policy
from unittest.mock import AsyncMock, MagicMock, patch

from desk.channels.email import (
    EmailChannel,
    InboundEmail,
    compute_thread_id,
    parse_email_message,
)
from desk.config import Settings

RAW_NEW_EMAIL = """\
From: Carlos Rivera <carlos@example.com>
To: support@desk.local
Subject: Help with my order
Message-ID: <msg-001@example.com>
Content-Type: text/plain; charset=utf-8

Hello, where is my order?
"""

RAW_REPLY_EMAIL = """\
From: Carlos Rivera <carlos@example.com>
To: support@desk.local
Subject: Re: Help with my order
Message-ID: <msg-002@example.com>
In-Reply-To: <msg-001@example.com>
References: <msg-001@example.com>
Content-Type: text/plain; charset=utf-8

Thanks, still waiting though.
"""


def _settings(**overrides) -> Settings:
    """Build a Settings instance with explicit email overrides (no lru cache)."""
    base = {
        "email_enabled": False,
        "email_smtp_host": "",
        "email_smtp_port": 587,
        "email_smtp_user": "",
        "email_smtp_password": "",
        "email_use_tls": True,
        "email_from": "",
    }
    base.update(overrides)
    return Settings(**base)


class TestParseEmailMessage:
    """EM1 — pure RFC822 parsing."""

    def test_parses_from_subject_body(self):
        parsed = parse_email_message(RAW_NEW_EMAIL)
        assert parsed.from_address == "carlos@example.com"
        assert parsed.subject == "Help with my order"
        assert parsed.body == "Hello, where is my order?"

    def test_parses_message_id_and_to(self):
        parsed = parse_email_message(RAW_NEW_EMAIL)
        assert parsed.message_id == "msg-001@example.com"
        assert parsed.to_address == "support@desk.local"

    def test_parses_references_and_in_reply_to(self):
        parsed = parse_email_message(RAW_REPLY_EMAIL)
        assert parsed.in_reply_to == "msg-001@example.com"
        assert parsed.references == ["msg-001@example.com"]

    def test_parses_bytes_input(self):
        parsed = parse_email_message(RAW_NEW_EMAIL.encode())
        assert parsed.from_address == "carlos@example.com"
        assert parsed.body == "Hello, where is my order?"

    def test_missing_optional_headers_default_empty(self):
        raw = "From: a@b.com\nSubject: hi\n\nbody\n"
        parsed = parse_email_message(raw)
        assert parsed.message_id == ""
        assert parsed.in_reply_to == ""
        assert parsed.references == []


class TestThreadReuse:
    """EM2 — stable conversation id so replies reuse a conversation."""

    def test_top_level_mail_anchors_on_own_message_id(self):
        parsed = parse_email_message(RAW_NEW_EMAIL)
        # A top-level mail is keyed by its own Message-ID so replies can find it.
        assert compute_thread_id(parsed) == "email-msg:msg-001@example.com"

    def test_reply_reuses_thread_via_references(self):
        original = parse_email_message(RAW_NEW_EMAIL)
        reply = parse_email_message(RAW_REPLY_EMAIL)
        # The reply anchors on the original message-id -> same conversation id.
        assert compute_thread_id(reply) == compute_thread_id(original)
        assert compute_thread_id(reply) == "email-msg:msg-001@example.com"

    def test_no_message_id_falls_back_to_sender_subject(self):
        mail = InboundEmail(from_address="carlos@example.com", subject="No id topic", body="x")
        thread_id = compute_thread_id(mail)
        assert thread_id.startswith("email-thread:")
        # Deterministic for the same sender+subject.
        assert compute_thread_id(
            InboundEmail(from_address="carlos@example.com", subject="No id topic", body="y")
        ) == thread_id

    def test_different_subject_starts_new_conversation(self):
        other = InboundEmail(from_address="carlos@example.com", subject="Different topic", body="x")
        same = InboundEmail(from_address="carlos@example.com", subject="No id topic", body="x")
        assert compute_thread_id(other) != compute_thread_id(same)


class TestInboundRouting:
    """EM2 — inbound email is routed through the shared MessageRouter (mocked)."""

    async def test_inbound_creates_conversation_via_router(self):
        channel = EmailChannel(settings=_settings())
        with patch("desk.channels.email.MessageRouter") as router_cls:
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
            result = await channel.route_inbound(RAW_NEW_EMAIL, db, event_bus)

        router_cls.assert_called_once_with(db, event_bus)
        instance.route.assert_awaited_once()
        inbound = instance.route.await_args.args[0]
        assert inbound.channel == "email"
        assert inbound.sender_identifier == "carlos@example.com"
        assert inbound.content == "Hello, where is my order?"
        assert inbound.metadata["subject"] == "Help with my order"
        assert result["conversation_id"] == "conv-1"

    async def test_reply_routes_to_same_conversation_id(self):
        channel = EmailChannel(settings=_settings())
        captured = []
        with patch("desk.channels.email.MessageRouter") as router_cls:
            instance = router_cls.return_value
            instance.route = AsyncMock(
                side_effect=lambda inbound: captured.append(inbound.conversation_id)
                or {"conversation_id": inbound.conversation_id, "status": "routed"}
            )
            await channel.route_inbound(RAW_NEW_EMAIL, MagicMock(), MagicMock())
            await channel.route_inbound(RAW_REPLY_EMAIL, MagicMock(), MagicMock())

        # The original mail and its reply share one channel conversation id.
        assert len(captured) == 2
        assert captured[0] == captured[1]


class TestSendReply:
    """EM3 — outbound SMTP send shape + unconfigured stub."""

    def test_unconfigured_smtp_is_stubbed(self):
        factory = MagicMock()
        channel = EmailChannel(settings=_settings(email_enabled=False), smtp_factory=factory)
        result = channel.send_reply("carlos@example.com", "Re: Help", "On its way")
        assert result["success"] is True
        assert result["stubbed"] is True
        factory.assert_not_called()

    def test_enabled_but_no_host_is_stubbed(self):
        factory = MagicMock()
        channel = EmailChannel(settings=_settings(email_enabled=True), smtp_factory=factory)
        result = channel.send_reply("carlos@example.com", "Re: Help", "body")
        assert result["stubbed"] is True
        factory.assert_not_called()

    def test_configured_smtp_send_call_shape(self):
        smtp = MagicMock()
        factory = MagicMock(return_value=smtp)
        settings = _settings(
            email_enabled=True,
            email_smtp_host="smtp.test.invalid",
            email_smtp_port=2525,
            email_smtp_user="desk-user",
            email_smtp_password="desk-pass",
            email_from="support@desk.local",
        )
        channel = EmailChannel(settings=settings, smtp_factory=factory)

        result = channel.send_reply("carlos@example.com", "Re: Help with my order", "On its way")

        assert result["success"] is True
        assert result["stubbed"] is False
        assert result["message_id"]
        # Connection opened against the configured host/port.
        factory.assert_called_once_with("smtp.test.invalid", 2525)
        # STARTTLS + login (user configured) + send + quit.
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("desk-user", "desk-pass")
        smtp.quit.assert_called_once()

        smtp.sendmail.assert_called_once()
        sender, recipients, raw_msg = smtp.sendmail.call_args.args
        assert sender == "support@desk.local"
        assert recipients == ["carlos@example.com"]
        # Parse the generated MIME message back to assert on decoded content
        # (the body is base64-encoded by MIMEText for utf-8).
        sent = message_from_string(raw_msg, policy=policy.default)
        assert sent["Subject"] == "Re: Help with my order"
        assert sent["To"] == "carlos@example.com"
        assert sent["From"] == "support@desk.local"
        assert sent.get_content().strip() == "On its way"

    def test_no_login_when_user_empty(self):
        smtp = MagicMock()
        factory = MagicMock(return_value=smtp)
        settings = _settings(
            email_enabled=True,
            email_smtp_host="smtp.test.invalid",
            email_smtp_user="",
            email_from="support@desk.local",
        )
        channel = EmailChannel(settings=settings, smtp_factory=factory)
        result = channel.send_reply("a@b.com", "s", "b")
        assert result["success"] is True
        smtp.login.assert_not_called()

    def test_transport_error_returns_failure_without_raising(self):
        smtp = MagicMock()
        smtp.sendmail.side_effect = RuntimeError("connection reset")
        factory = MagicMock(return_value=smtp)
        settings = _settings(
            email_enabled=True, email_smtp_host="smtp.test.invalid", email_from="s@d.local"
        )
        channel = EmailChannel(settings=settings, smtp_factory=factory)
        result = channel.send_reply("a@b.com", "s", "b")
        assert result["success"] is False
        assert "connection reset" in result["error"]
        smtp.quit.assert_called_once()
