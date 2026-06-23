"""
ODW.ai Desk — Channel Schemas

Pydantic models for channel-specific messages and events.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """
    Canonical inbound message from any channel.

    All channel adapters normalize messages to this format before publishing
    to the event bus.
    """

    message_id: str = Field(..., description="Unique message identifier from channel")
    conversation_id: str = Field(..., description="Channel-specific conversation/thread ID")
    channel: Literal["whatsapp", "webchat", "email", "telegram", "discord", "slack", "signal"] = (
        Field(..., description="Channel type")
    )
    sender_identifier: str = Field(
        ..., description="Sender identifier (phone number, email, user ID)"
    )
    sender_type: Literal["customer", "agent", "system"] = Field(
        default="customer", description="Sender type"
    )
    content: str = Field(..., description="Message text content")
    media_urls: list[str] = Field(default_factory=list, description="Media file URLs")
    metadata: dict = Field(default_factory=dict, description="Channel-specific metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "wamid.abc123",
                "conversation_id": "wa_thread_12345",
                "channel": "whatsapp",
                "sender_identifier": "+5511999887766",
                "sender_type": "customer",
                "content": "Hi, I need help with my appointment",
                "media_urls": [],
                "metadata": {"whatsapp_message_type": "text"},
                "timestamp": "2026-06-24T10:00:00Z",
            }
        }


class OutboundMessage(BaseModel):
    """
    Outbound message to be sent via a channel.

    Created by AI Engine or human agents, delivered by OutboundDispatcher.
    """

    conversation_id: str = Field(..., description="Channel-specific conversation/thread ID")
    channel: Literal["whatsapp", "webchat", "email", "telegram", "discord", "slack", "signal"] = (
        Field(..., description="Channel type")
    )
    recipient_identifier: str = Field(
        ..., description="Recipient identifier (phone number, email, user ID)"
    )
    content: str = Field(..., description="Message text content")
    media_urls: list[str] = Field(default_factory=list, description="Media file URLs")
    metadata: dict = Field(default_factory=dict, description="Channel-specific metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "wa_thread_12345",
                "channel": "whatsapp",
                "recipient_identifier": "+5511999887766",
                "content": "Hi Carlos! How can I help you today?",
                "media_urls": [],
                "metadata": {},
            }
        }


class DeliveryResult(BaseModel):
    """Result of outbound message delivery attempt."""

    success: bool = Field(..., description="Whether delivery succeeded")
    channel_message_id: str | None = Field(
        default=None, description="Channel-assigned message ID"
    )
    error: str | None = Field(default=None, description="Error message if delivery failed")
    delivered_at: datetime = Field(
        default_factory=datetime.utcnow, description="Delivery timestamp"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "channel_message_id": "wamid.xyz789",
                "error": None,
                "delivered_at": "2026-06-24T10:01:00Z",
            }
        }


class WebChatSession(BaseModel):
    """Web chat session information."""

    session_id: str = Field(..., description="Unique session identifier")
    customer_identifier: str | None = Field(
        default=None, description="Customer identifier (if authenticated)"
    )
    metadata: dict = Field(default_factory=dict, description="Session metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation time")


class EmailMessage(BaseModel):
    """Email-specific message structure."""

    message_id: str = Field(..., description="Email message ID")
    from_address: str = Field(..., description="Sender email address")
    to_address: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body_text: str = Field(default="", description="Plain text body")
    body_html: str = Field(default="", description="HTML body")
    attachments: list[str] = Field(default_factory=list, description="Attachment file paths")
    received_at: datetime = Field(
        default_factory=datetime.utcnow, description="Email received timestamp"
    )
