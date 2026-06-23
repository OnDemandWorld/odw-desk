"""
ODW.ai Desk — Event Schemas

Pydantic models for event bus payloads.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from desk.schemas.channels import InboundMessage, OutboundMessage


class InboundMessageEvent(BaseModel):
    """Event published when an inbound message is received from a channel."""

    event_type: Literal["inbound.message"] = "inbound.message"
    message: InboundMessage = Field(..., description="Inbound message data")
    received_at: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )


class OutboundMessageEvent(BaseModel):
    """Event published when an outbound message is ready to be sent."""

    event_type: Literal["outbound.message"] = "outbound.message"
    message: OutboundMessage = Field(..., description="Outbound message data")
    ai_generated: bool = Field(default=False, description="Whether message was AI-generated")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="AI confidence score (if AI-generated)"
    )
    prepared_at: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )


class ConversationStateEvent(BaseModel):
    """Event published when a conversation state changes."""

    event_type: Literal[
        "conversation.created",
        "conversation.updated",
        "conversation.escalated",
        "conversation.resolved",
    ] = Field(..., description="Event type")
    conversation_id: str = Field(..., description="Conversation ID")
    old_state: str | None = Field(default=None, description="Previous state")
    new_state: str = Field(..., description="New state")
    reason: str | None = Field(default=None, description="Reason for state change")
    changed_at: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )


class AIDecisionEvent(BaseModel):
    """Event published when AI makes a decision (response, escalation, etc.)."""

    event_type: Literal["ai.decision"] = "ai.decision"
    conversation_id: str = Field(..., description="Conversation ID")
    message_id: str = Field(..., description="Message ID that triggered decision")
    decision: Literal["respond", "escalate", "fallback"] = Field(
        ..., description="AI decision"
    )
    model_used: str = Field(..., description="Model used for inference")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    routing_decision: dict = Field(
        default_factory=dict, description="Model routing decision details"
    )
    decided_at: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )


class SLABreachEvent(BaseModel):
    """Event published when an SLA is breached."""

    event_type: Literal["sla.breach"] = "sla.breach"
    conversation_id: str = Field(..., description="Conversation ID")
    sla_type: Literal["first_response", "resolution"] = Field(
        ..., description="SLA type that was breached"
    )
    due_at: datetime = Field(..., description="When SLA was due")
    breached_at: datetime = Field(
        default_factory=datetime.utcnow, description="When breach was detected"
    )


class AgentActionEvent(BaseModel):
    """Event published when a human agent performs an action."""

    event_type: Literal[
        "agent.takeover",
        "agent.respond",
        "agent.resolve",
        "agent.assign",
    ] = Field(..., description="Event type")
    conversation_id: str = Field(..., description="Conversation ID")
    agent_id: str = Field(..., description="Agent ID")
    action_details: dict = Field(default_factory=dict, description="Action-specific details")
    performed_at: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
