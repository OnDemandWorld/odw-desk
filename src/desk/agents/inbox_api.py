"""
ODW.ai Desk — Agent Inbox REST API (AGENT-001)

Human agent interface for conversation management, message history,
response composition, and takeover/handoff actions.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from desk.conversations.manager import ConversationManager
from desk.conversations.state_machine import ConversationStatus
from desk.dependencies import get_db
from desk.models.agent import Agent
from desk.models.conversation import Conversation
from desk.models.message import Message

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Inbox"])


@router.get("/conversations", response_model=list[dict])
async def list_conversations(
    status: str | None = Query(None, description="Filter by status"),
    assigned_agent_id: UUID | None = Query(None, description="Filter by assigned agent"),
    channel: str | None = Query(None, description="Filter by channel"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    List conversations with optional filters.

    Returns conversations sorted by updated_at (most recent first).
    """
    query = select(Conversation).options(
        selectinload(Conversation.customer),
        selectinload(Conversation.assigned_agent),
    )

    if status:
        query = query.where(Conversation.status == status)
    if assigned_agent_id:
        query = query.where(Conversation.assigned_agent_id == assigned_agent_id)
    if channel:
        query = query.where(Conversation.channel == channel)

    query = query.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return [
        {
            "id": str(conv.id),
            "customer_id": str(conv.customer_id),
            "customer_identifier": conv.customer.channel_identifiers if conv.customer else None,
            "channel": conv.channel,
            "channel_conversation_id": conv.channel_conversation_id,
            "status": conv.status,
            "assigned_agent_id": str(conv.assigned_agent_id) if conv.assigned_agent_id else None,
            "assigned_agent_name": conv.assigned_agent.display_name if conv.assigned_agent else None,
            "ai_enabled": conv.ai_enabled,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        }
        for conv in conversations
    ]


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
    agent_id: UUID = Query(..., description="Agent ID sending response"),
    content: str = Query(..., description="Response content"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Send a response as a human agent.
    """
    conversation_manager = ConversationManager(db)

    # Get conversation
    query = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
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
