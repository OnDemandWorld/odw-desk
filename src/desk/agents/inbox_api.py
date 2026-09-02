"""
ODW.ai Desk — Agent Inbox REST API (AGENT-001)

Human agent interface for conversation management, message history,
response composition, and takeover/handoff actions.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from desk.agents.websocket import broadcast_conversation_update
from desk.channels.outbound import OutboundDispatcher
from desk.conversations.manager import ConversationManager
from desk.conversations.state_machine import ConversationStatus
from desk.dependencies import get_db
from desk.models.agent import Agent
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message
from desk.schemas.channels import OutboundMessage

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Inbox"])


@router.get("/conversations", response_model=list[dict])
async def list_conversations(
    status: str | None = Query(None, description="Filter by status"),
    assigned_agent_id: UUID | None = Query(None, description="Filter by assigned agent"),
    unassigned: bool = Query(False, description="Only unassigned (open-queue) conversations"),
    channel: str | None = Query(None, description="Filter by channel"),
    q: str | None = Query(
        None, min_length=1, max_length=200, description="Search customer name/identifier or channel conversation ID"
    ),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    response: Response = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    List conversations with optional filters, search, and pagination.

    Returns conversations sorted by updated_at (most recent first), enriched
    with the customer display name, unread customer-message count, and a
    last-message preview. The ``X-Total-Count`` response header carries the
    total number of conversations matching the filters (Chatwoot-style
    pagination metadata) so clients can page without a shape change.
    """
    conditions = []
    if status:
        conditions.append(Conversation.status == status)
    if assigned_agent_id is not None:
        conditions.append(Conversation.assigned_agent_id == assigned_agent_id)
    if unassigned:
        conditions.append(Conversation.assigned_agent_id.is_(None))
    if channel:
        conditions.append(Conversation.channel == channel)

    query = select(Conversation).options(
        selectinload(Conversation.customer),
        selectinload(Conversation.assigned_agent),
    )
    count_query = select(func.count()).select_from(Conversation)

    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                Customer.display_name.ilike(like),
                Conversation.channel_conversation_id.ilike(like),
                cast(Customer.channel_identifiers, String).ilike(like),
            )
        )
        # The search predicate references customers, so both queries join it.
        query = query.join(Conversation.customer)
        count_query = count_query.join(Conversation.customer)

    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)
    conversations = (await db.execute(query)).scalars().all()

    # Batch enrichment (2 extra queries per page instead of 2 per row):
    # unread customer messages and the latest message per conversation
    # (DISTINCT ON keeps this to a single scan on PostgreSQL).
    conversation_ids = [conv.id for conv in conversations]
    unread_by_conv: dict = {}
    last_message_by_conv: dict = {}
    if conversation_ids:
        unread_result = await db.execute(
            select(Message.conversation_id, func.count())
            .where(
                Message.conversation_id.in_(conversation_ids),
                Message.sender_type == "customer",
                Message.read_at.is_(None),
            )
            .group_by(Message.conversation_id)
        )
        unread_by_conv = dict(unread_result.all())

        last_result = await db.execute(
            select(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .distinct(Message.conversation_id)
            .order_by(Message.conversation_id, Message.created_at.desc())
        )
        last_message_by_conv = {msg.conversation_id: msg for msg in last_result.scalars()}

    response.headers["X-Total-Count"] = str(total)

    items = []
    for conv in conversations:
        last = last_message_by_conv.get(conv.id)
        preview = (last.content[:140] + "…") if last and len(last.content) > 140 else (last.content if last else None)
        items.append(
            {
                "id": str(conv.id),
                "customer_id": str(conv.customer_id),
                "customer_name": conv.customer.display_name if conv.customer else None,
                "customer_identifier": conv.customer.channel_identifiers if conv.customer else None,
                "channel": conv.channel,
                "channel_conversation_id": conv.channel_conversation_id,
                "status": conv.status,
                "assigned_agent_id": str(conv.assigned_agent_id) if conv.assigned_agent_id else None,
                "assigned_agent_name": conv.assigned_agent.display_name if conv.assigned_agent else None,
                "ai_enabled": conv.ai_enabled,
                "unread_count": unread_by_conv.get(conv.id, 0),
                "last_message": (
                    {
                        "content": preview,
                        "sender_type": last.sender_type,
                        "created_at": last.created_at.isoformat() if last.created_at else None,
                    }
                    if last
                    else None
                ),
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            }
        )
    return items


@router.get("/conversations/{conversation_id}", response_model=dict)
async def get_conversation_detail(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get conversation detail with full message history.
    """
    query = (
        select(Conversation)
        .options(
            selectinload(Conversation.customer),
            selectinload(Conversation.assigned_agent),
            selectinload(Conversation.messages),
        )
        .where(Conversation.id == conversation_id)
    )

    result = await db.execute(query)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "id": str(conversation.id),
        "customer_id": str(conversation.customer_id),
        "customer": {
            "id": str(conversation.customer.id),
            "channel_identifiers": conversation.customer.channel_identifiers,
            "metadata": conversation.customer.metadata_,
        } if conversation.customer else None,
        "channel": conversation.channel,
        "channel_conversation_id": conversation.channel_conversation_id,
        "status": conversation.status,
        "assigned_agent_id": str(conversation.assigned_agent_id) if conversation.assigned_agent_id else None,
        "assigned_agent": {
            "id": str(conversation.assigned_agent.id),
            "name": conversation.assigned_agent.display_name,
            "email": conversation.assigned_agent.email,
        } if conversation.assigned_agent else None,
        "ai_enabled": conversation.ai_enabled,
        "confidence_threshold": conversation.confidence_threshold,
        "sla_first_response_due": conversation.sla_first_response_due.isoformat() if conversation.sla_first_response_due else None,
        "sla_resolution_due": conversation.sla_resolution_due.isoformat() if conversation.sla_resolution_due else None,
        "metadata": conversation.metadata_,
        "messages": [
            {
                "id": str(msg.id),
                "sender_type": msg.sender_type,
                "sender_id": msg.sender_id,
                "content": msg.content,
                "content_redacted": msg.content_redacted,
                "pii_detected": msg.pii_detected,
                "pii_types": msg.pii_types,
                "persona_backend_used": msg.persona_backend_used,
                "confidence_score": (msg.metadata_ or {}).get("confidence"),
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in sorted(conversation.messages, key=lambda m: m.created_at)
        ],
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
    }


@router.post("/conversations/{conversation_id}/takeover")
async def take_over_conversation(
    conversation_id: UUID,
    agent_id: UUID = Query(..., description="Agent ID taking over"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Take over a conversation (escalated → active, agent-assigned).

    Transitions conversation from escalated to active and assigns to agent.
    """
    conversation_manager = ConversationManager(db)

    # Get conversation
    query = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(query)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get agent
    agent_query = select(Agent).where(Agent.id == agent_id)
    agent_result = await db.execute(agent_query)
    agent = agent_result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Assign agent and update status
    await conversation_manager.assign_agent(conversation, agent)

    # Transition to active if escalated
    if conversation.status == ConversationStatus.ESCALATED:
        await conversation_manager.update_status(
            conversation,
            ConversationStatus.ACTIVE,
            reason=f"Taken over by agent {agent.display_name}",
        )

    await db.commit()

    logger.info(
        "Conversation taken over",
        conversation_id=str(conversation_id),
        agent_id=str(agent_id),
        agent_name=agent.display_name,
    )

    return {
        "success": True,
        "conversation_id": str(conversation_id),
        "agent_id": str(agent_id),
        "status": conversation.status,
    }


@router.post("/conversations/{conversation_id}/respond")
async def send_agent_response(
    conversation_id: UUID,
    request: Request,
    agent_id: UUID = Query(..., description="Agent ID sending response"),
    content: str = Query(..., description="Response content"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Send a response as a human agent.

    Persists the message and dispatches it to the customer over their
    channel via the outbound dispatcher.
    """
    conversation_manager = ConversationManager(db)

    # Get conversation
    query = (
        select(Conversation)
        .options(
            selectinload(Conversation.messages),
            selectinload(Conversation.customer),
        )
        .where(Conversation.id == conversation_id)
    )
    result = await db.execute(query)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get agent
    agent_query = select(Agent).where(Agent.id == agent_id)
    agent_result = await db.execute(agent_query)
    agent = agent_result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify agent is assigned to this conversation
    if conversation.assigned_agent_id != agent_id:
        raise HTTPException(
            status_code=403,
            detail="Agent not assigned to this conversation. Take over first.",
        )

    # Add message
    message = await conversation_manager.add_message(
        conversation=conversation,
        sender_type="agent",
        sender_id=str(agent_id),
        content=content,
        metadata={"agent_name": agent.display_name},
    )

    await db.commit()

    # Deliver the reply to the customer over their channel. Previously the
    # message was only persisted — the customer never actually received it.
    dispatcher: OutboundDispatcher | None = getattr(
        request.app.state, "outbound_dispatcher", None
    )
    if dispatcher is not None and conversation.customer is not None:
        recipient = (conversation.customer.channel_identifiers or {}).get(
            conversation.channel
        )
        if recipient:
            delivery = await dispatcher.dispatch(
                OutboundMessage(
                    conversation_id=str(conversation.id),
                    channel=conversation.channel,
                    recipient_identifier=recipient,
                    content=content,
                    metadata={"sender": "agent", "message_id": str(message.id)},
                )
            )
            logger.info(
                "Agent reply dispatched to channel",
                conversation_id=str(conversation_id),
                channel=conversation.channel,
                delivery=delivery,
            )
        else:
            logger.warning(
                "Agent reply not dispatched: no recipient identifier for channel",
                conversation_id=str(conversation_id),
                channel=conversation.channel,
            )

    logger.info(
        "Agent response sent",
        conversation_id=str(conversation_id),
        agent_id=str(agent_id),
        message_id=str(message.id),
    )

    return {
        "success": True,
        "message_id": str(message.id),
        "conversation_id": str(conversation_id),
    }


@router.post("/conversations/{conversation_id}/resolve")
async def resolve_conversation(
    conversation_id: UUID,
    agent_id: UUID = Query(..., description="Agent ID resolving"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Resolve a conversation.
    """
    conversation_manager = ConversationManager(db)

    # Get conversation
    query = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(query)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Transition to resolved
    await conversation_manager.update_status(
        conversation,
        ConversationStatus.RESOLVED,
        reason=f"Resolved by agent {agent_id}",
    )

    await db.commit()

    logger.info(
        "Conversation resolved",
        conversation_id=str(conversation_id),
        agent_id=str(agent_id),
    )

    return {
        "success": True,
        "conversation_id": str(conversation_id),
        "status": conversation.status,
    }


class ConversationStatusUpdate(BaseModel):
    """Request body for FSM-validated conversation status updates."""

    status: Literal["new", "active", "pending", "escalated", "resolved", "closed"]
    reason: str | None = Field(None, max_length=500)


@router.post("/conversations/{conversation_id}/status")
async def update_conversation_status(
    conversation_id: UUID,
    payload: ConversationStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Update a conversation's status with state-machine validation.

    Centralizes status changes (open/pending/escalate/resolve/close) behind
    the FSM instead of ad-hoc per-action endpoints; invalid transitions are
    rejected with 400 rather than silently corrupting the lifecycle. Status
    changes are broadcast to subscribed agents over the websocket.
    """
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        await ConversationManager(db).update_status(
            conversation,
            ConversationStatus(payload.status),
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()

    await broadcast_conversation_update(
        str(conversation.id),
        {"status": conversation.status, "reason": payload.reason},
    )

    logger.info(
        "Conversation status updated",
        conversation_id=str(conversation_id),
        status=payload.status,
    )

    return {
        "success": True,
        "conversation_id": str(conversation_id),
        "status": conversation.status,
    }


@router.post("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Mark all unread customer messages in a conversation as read.

    Backs the inbox unread badge: an agent opening a conversation clears its
    unread customer messages (read receipts, V1.6 F-4).
    """
    exists_result = await db.execute(
        select(Conversation.id).where(Conversation.id == conversation_id)
    )
    if exists_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_type == "customer",
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(tz=UTC))
    )
    await db.commit()

    return {
        "success": True,
        "conversation_id": str(conversation_id),
        "marked_read": result.rowcount,
    }


@router.post("/messages/{message_id}/feedback")
async def provide_ai_feedback(
    message_id: UUID,
    feedback: str = Query(..., description="Feedback: 'thumbs_up' or 'thumbs_down'"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Provide feedback on an AI response (thumbs up/down).
    """
    if feedback not in ["thumbs_up", "thumbs_down"]:
        raise HTTPException(
            status_code=400,
            detail="Feedback must be 'thumbs_up' or 'thumbs_down'",
        )

    # Get message
    query = select(Message).where(Message.id == message_id)
    result = await db.execute(query)
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_type != "ai":
        raise HTTPException(
            status_code=400,
            detail="Feedback can only be provided on AI messages",
        )

    # Update metadata with feedback
    metadata = message.metadata_ or {}
    metadata["agent_feedback"] = feedback
    message.metadata_ = metadata

    await db.commit()

    logger.info(
        "AI feedback received",
        message_id=str(message_id),
        feedback=feedback,
    )

    return {
        "success": True,
        "message_id": str(message_id),
        "feedback": feedback,
    }


@router.get("/agents", response_model=list[dict])
async def list_agents(
    online_only: bool = Query(False, description="Only show online agents"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    List all agents with their status.
    """
    query = select(Agent)
    if online_only:
        query = query.where(Agent.is_online == True)  # noqa: E712

    result = await db.execute(query)
    agents = result.scalars().all()

    return [
        {
            "id": str(agent.id),
            "name": agent.display_name,
            "email": agent.email,
            "role": agent.role,
            "is_online": agent.is_online,
            "active_conversations": len(agent.assigned_conversations) if agent.assigned_conversations else 0,
            "created_at": agent.created_at.isoformat() if agent.created_at else None,
        }
        for agent in agents
    ]
