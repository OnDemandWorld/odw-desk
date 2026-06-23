"""
ODW.ai Desk — API Schemas

Pydantic models for API request/response bodies.
"""

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ..., description="Health status"
    )
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Deployment environment")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Health check timestamp"
    )


class RootResponse(BaseModel):
    """Root endpoint response."""

    name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    docs: str | None = Field(default=None, description="API documentation URL")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict | None = Field(default=None, description="Additional error details")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    channel: Literal["whatsapp", "webchat", "email"] = Field(..., description="Channel type")
    customer_identifier: str = Field(
        ..., description="Customer identifier (phone, email, etc.)"
    )
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""

    content: str = Field(..., description="Message content", min_length=1, max_length=10000)
    media_urls: list[str] = Field(default_factory=list, description="Media file URLs")


class UpdateConversationStatusRequest(BaseModel):
    """Request to update conversation status."""

    status: Literal["active", "pending", "escalated", "resolved"] = Field(
        ..., description="New conversation status"
    )
    reason: str | None = Field(default=None, description="Reason for status change")


class AgentTakeoverRequest(BaseModel):
    """Request for human agent to take over a conversation."""

    agent_id: str = Field(..., description="Agent ID taking over")
    note: str | None = Field(default=None, description="Optional note about takeover")
