"""
ODW.ai Desk — Email Channel Adapter (V1.5 F-2, EM1-EM3)

Adds an Email channel that shares the existing conversation/agent pipeline with
WhatsApp and Web-chat. Inbound mail is parsed from RFC822 into a canonical
:class:`InboundMessage` (``channel="email"``) and handed to the shared
:class:`MessageRouter`, which resolves/creates the customer + conversation and
persists the message. Outbound replies are delivered over SMTP via
:meth:`EmailChannel.send_reply`; the SMTP transport is injectable so tests can
assert the call shape, and when SMTP is not configured the send is gracefully
stubbed so development never requires a live mail server.

Threading: a stable channel conversation id is derived from the mail's
``References``/``In-Reply-To`` anchors (so a reply reuses the original
conversation) or, failing that, from ``sender + subject`` (so a fresh top-level
mail starts a new conversation).
"""

import asyncio
import email
import hashlib
import smtplib
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.utils import make_msgid, parseaddr
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from desk.channels.base import AdapterConfig, AdapterHealthStatus, ChannelAdapter
from desk.config import Settings, get_settings
from desk.dependencies import get_db, get_event_bus
from desk.observability.metrics import MESSAGES_RECEIVED
from desk.observability.tracing import get_current_trace_id, start_span
from desk.router.message_router import MessageRouter
from desk.schemas.channels import InboundMessage, OutboundMessage

logger = structlog.get_logger()

EMAIL_CHANNEL = "email"

# Inbound webhook relay (Mailgun routes / SendGrid inbound parse / CloudMailin
# style). Kept under the same unguarded webhook prefix as WhatsApp.
router = APIRouter(prefix="/api/v1/webhooks", tags=["Email"])


@dataclass
class InboundEmail:
    """A parsed inbound email (normalized RFC822 fields)."""

    from_address: str
    subject: str
    body: str
    message_id: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    to_address: str = ""
    from_display_name: str = ""


def _normalize_message_id(value: str | None) -> str:
    """Normalize an RFC822 message-id: strip angle brackets/whitespace, lowercase."""
    return (value or "").strip().strip("<>").strip().lower()


def parse_email_message(raw: str | bytes) -> InboundEmail:
    """
    Parse a raw RFC822 message into an :class:`InboundEmail` (pure function).

    Uses the stdlib ``email`` package with the modern ``policy.default`` so
    encoded headers are decoded and the preferred body part is selected cleanly.
    Prefers ``text/plain``; falls back to ``text/html`` when no plain part exists.

    Args:
        raw: The full RFC822 message (headers + body) as str or bytes.

    Returns:
        Normalized InboundEmail (from/subject/body/message_id/references/...).
    """
    if isinstance(raw, bytes):
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    else:
        msg = email.message_from_string(raw, policy=email.policy.default)

    from_header = msg.get("From") or ""
    from_display_name, from_addr = parseaddr(from_header)
    from_address = from_addr or from_header.strip()

    body_part = msg.get_body(preferencelist=("plain",)) or msg.get_body(preferencelist=("html",))
    if body_part is not None:
        content = body_part.get_content()
        body = content.strip() if isinstance(content, str) else ""
    else:
        body = ""

    references_header = msg.get("References") or ""
    references = [_normalize_message_id(r) for r in references_header.split() if r.strip()]

    return InboundEmail(
        from_address=from_address,
        to_address=(msg.get("To") or "").strip(),
        from_display_name=(from_display_name or "").strip(),
        subject=(msg.get("Subject") or "").strip(),
        body=body,
        message_id=_normalize_message_id(msg.get("Message-ID")),
        in_reply_to=_normalize_message_id(msg.get("In-Reply-To")),
        references=references,
    )


def compute_thread_id(msg: InboundEmail) -> str:
    """
    Derive a stable channel conversation id for an inbound email.

    Threading anchors on the RFC822 message-id of the thread root:
    - A reply carries the root id in ``References`` (oldest first) /
      ``In-Reply-To``, so it maps to the root's conversation.
    - A top-level mail anchors on its *own* ``Message-ID``, so a later reply
      referencing it lands on the same conversation id.
    - With no message-id at all, fall back to ``sender + subject`` so mails on
      the same topic from the same sender still share a conversation.
    """
    anchor = next((r for r in msg.references if r), "") or msg.in_reply_to or msg.message_id
    if anchor:
        return f"email-msg:{anchor}"
    digest = hashlib.sha1(f"{msg.from_address}|{msg.subject}".encode()).hexdigest()[:16]
    return f"email-thread:{digest}"


class EmailChannel:
    """
    Email channel adapter (inbound routing + outbound SMTP replies).

    The SMTP transport is injectable via ``smtp_factory`` (a callable
    ``(host, port) -> SMTP-like object``) so tests can assert the send shape
    without a live server. When SMTP is not configured (``email_enabled`` False
    or no host), :meth:`send_reply` returns a stubbed success.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        smtp_factory: Callable[[str, int], object] | None = None,
    ):
        self.settings = settings or get_settings()
        self.smtp_factory = smtp_factory

    def build_inbound_message(self, msg: InboundEmail) -> InboundMessage:
        """Normalize a parsed email into the canonical inbound message."""
        return InboundMessage(
            message_id=msg.message_id or f"email-{uuid.uuid4().hex}",
            conversation_id=compute_thread_id(msg),
            channel=EMAIL_CHANNEL,
            sender_identifier=msg.from_address,
            sender_name=msg.from_display_name or None,
            sender_type="customer",
            content=msg.body,
            media_urls=[],
            metadata={
                "channel": EMAIL_CHANNEL,
                "subject": msg.subject,
                "message_id": msg.message_id,
                "in_reply_to": msg.in_reply_to,
                "references": msg.references,
                "to": msg.to_address,
            },
        )

    async def route_inbound(self, raw: str | bytes, db, event_bus) -> dict:
        """
        Parse a raw inbound email and route it through the shared MessageRouter.

        Creates/reuses the customer + conversation (thread reuse via
        :func:`compute_thread_id`) and persists the message exactly like the
        WhatsApp/Web-chat paths.
        """
        inbound = self.build_inbound_message(parse_email_message(raw))
        message_router = MessageRouter(db, event_bus)
        return await message_router.route(inbound)

    def _open_smtp(self, host: str, port: int):
        """Open an SMTP connection via the injected factory or stdlib smtplib."""
        if self.smtp_factory is not None:
            return self.smtp_factory(host, port)
        return smtplib.SMTP(host, port)

    def send_reply(self, to: str, subject: str, body: str) -> dict:
        """
        Send an outbound email reply over SMTP.

        When SMTP is not configured (``email_enabled`` False or no host) this is
        a graceful dev stub — no connection is attempted and a stubbed success is
        returned. Otherwise builds a ``text/plain`` MIME message (echoing the
        current ``X-Trace-Id`` best-effort) and delivers it via SMTP. Never
        raises: transport failures return ``{"success": False, ...}``.

        Args:
            to: Recipient email address.
            subject: Reply subject.
            body: Plain-text body.

        Returns:
            Result dict with ``success`` and the outbound ``message_id``.
        """
        settings = self.settings
        if not settings.email_enabled or not settings.email_smtp_host:
            logger.warning(
                "Email SMTP not configured; outbound reply is stubbed",
                recipient=to,
                subject=subject,
            )
            return {
                "success": True,
                "stubbed": True,
                "message_id": None,
                "message": "Email send stubbed (SMTP not configured)",
            }

        # Derive the Message-ID domain from the sender address; passing an
        # explicit domain keeps make_msgid from calling socket.getfqdn() (which
        # can block on a DNS lookup) and yields a stable, routable-looking id.
        from_address = settings.email_from or "desk@localhost"
        domain = from_address.split("@")[-1] if "@" in from_address else "desk.local"
        message_id = make_msgid(domain=domain or "desk.local")
        mime = MIMEText(body, "plain", "utf-8")
        mime["From"] = from_address
        mime["To"] = to
        mime["Subject"] = subject
        mime["Message-ID"] = message_id
        trace_id = get_current_trace_id()
        if trace_id:
            mime["X-Trace-Id"] = trace_id

        try:
            smtp = self._open_smtp(settings.email_smtp_host, settings.email_smtp_port)
            try:
                if settings.email_use_tls:
                    smtp.starttls()
                if settings.email_smtp_user:
                    smtp.login(settings.email_smtp_user, settings.email_smtp_password)
                smtp.sendmail(mime["From"], [to], mime.as_string())
            finally:
                smtp.quit()

            logger.info("Email reply sent", recipient=to, subject=subject)
            return {
                "success": True,
                "stubbed": False,
                "message_id": message_id,
                "message": "Email reply sent",
            }
        except Exception as exc:  # noqa: BLE001 - best-effort, never raise
            logger.error("Email send failed", recipient=to, error=str(exc))
            return {
                "success": False,
                "stubbed": False,
                "message_id": None,
                "error": str(exc),
            }


# Global instance (mirrors the WhatsApp/Web-chat adapter pattern).
_email_channel: EmailChannel | None = None


def get_email_channel() -> EmailChannel:
    """Get or create the global EmailChannel instance."""
    global _email_channel
    if _email_channel is None:
        _email_channel = EmailChannel()
    return _email_channel


class EmailChannelAdapter(ChannelAdapter):
    """
    Outbound adapter delivering AI/agent replies to customers over SMTP.

    Wraps :meth:`EmailChannel.send_reply`; SMTP is blocking, so the send is
    offloaded to a worker thread via :func:`asyncio.to_thread`. Inbound mail
    arrives via the ``POST /api/v1/webhooks/email`` relay endpoint, so this
    adapter only implements ``send`` plus the bookkeeping the channel
    manager expects. Registering it lets the OutboundDispatcher reach email
    customers, which was previously a dead end.
    """

    def __init__(self, email_channel: EmailChannel | None = None) -> None:
        super().__init__(
            AdapterConfig(
                adapter_id="email",
                adapter_name="Email",
                channel_type=EMAIL_CHANNEL,
                enabled=True,
            )
        )
        self.email_channel = email_channel or get_email_channel()

    async def connect(self) -> None:
        """Mark connected; SMTP connections are opened per send."""
        self.update_health("healthy", connected=True)

    async def disconnect(self) -> None:
        self.update_health("unhealthy", connected=False)

    async def receive(self) -> AsyncIterator[InboundMessage]:  # pragma: no cover
        # Inbound mail is handled by the webhook relay endpoint.
        yield

    async def send(self, message: OutboundMessage) -> dict[str, Any]:
        """Deliver a reply over SMTP (thread-offloaded; never raises)."""
        subject = (message.metadata or {}).get("subject") or "Re: your inquiry"
        result = await asyncio.to_thread(
            self.email_channel.send_reply,
            message.recipient_identifier,
            subject,
            message.content,
        )
        self.health_status.messages_sent += 1
        if not result.get("success"):
            self.health_status.last_error = str(result.get("error") or "send failed")
        return result

    async def health_check(self) -> AdapterHealthStatus:
        return self.health_status


@router.post("/email")
async def email_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Email inbound relay webhook.

    Accepts either a raw RFC822 message body (``message/rfc822`` /
    ``text/plain``) or a JSON envelope ``{"raw": "<rfc822>"}`` — the shapes
    inbound-relay services (Mailgun routes, SendGrid inbound parse, CloudMailin)
    can be configured to POST. The raw mail is parsed, threaded onto a
    conversation via ``References``/``In-Reply-To``, and routed through the
    shared MessageRouter exactly like the WhatsApp/Web-chat paths.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        raw: str | bytes = str(payload.get("raw") or payload.get("body") or "")
    else:
        raw = await request.body()

    if not raw or not str(raw).strip():
        raise HTTPException(status_code=400, detail="Empty email payload")

    # Observability: count inbound mail received on this channel.
    MESSAGES_RECEIVED.labels(channel=EMAIL_CHANNEL, status="received").inc()

    channel = get_email_channel()
    event_bus = get_event_bus()

    # Best-effort span so inbound mail joins the request's trace tree.
    with start_span("channel.email.inbound", {"channel": EMAIL_CHANNEL}):
        result = await channel.route_inbound(raw, db, event_bus)

    return JSONResponse(content={"status": "received", "routed": result})


__all__ = [
    "EMAIL_CHANNEL",
    "EmailChannel",
    "EmailChannelAdapter",
    "InboundEmail",
    "compute_thread_id",
    "get_email_channel",
    "parse_email_message",
]
