"""
ODW.ai Desk — Public CSAT API (Chatwoot-parity, round 2)

Customer-satisfaction survey collection for resolved conversations.

The conversation UUID acts as an unguessable capability token — the same
model Chatwoot uses for its CSAT survey links — so the endpoints are public
(no API key) and safe to embed in a survey link sent with the resolution
message. Ratings are stored on ``Conversation.metadata_["csat"]``; one
rating per conversation.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.dependencies import get_db
from desk.models.conversation import Conversation

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/public/csat", tags=["CSAT"])

RATEABLE_STATUSES = ("resolved", "closed")


class CSATSubmission(BaseModel):
    """CSAT survey submission (1 = very dissatisfied … 5 = very satisfied)."""

    score: int = Field(..., ge=1, le=5, description="Satisfaction score from 1 to 5")
    comment: str | None = Field(None, max_length=2000, description="Optional free-text feedback")


def _existing_csat(conversation: Conversation) -> dict | None:
    """Return the stored CSAT payload, if any."""
    csat = (conversation.metadata_ or {}).get("csat")
    return csat if isinstance(csat, dict) else None


async def _get_conversation(conversation_id: UUID, db: AsyncSession) -> Conversation:
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/{conversation_id}", response_model=dict)
async def get_csat(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Survey-page status: whether the conversation can be (or has been) rated.

    Powers the rating widget: shows the current score after submission and
    a friendly "not rateable yet" state while the conversation is still open.
    """
    conversation = await _get_conversation(conversation_id, db)
    csat = _existing_csat(conversation)

    return {
        "conversation_id": str(conversation.id),
        "status": conversation.status,
        "rateable": conversation.status in RATEABLE_STATUSES and csat is None,
        "already_rated": csat is not None,
        "score": csat.get("score") if csat else None,
        "comment": csat.get("comment") if csat else None,
        "rated_at": csat.get("rated_at") if csat else None,
    }


@router.post("/{conversation_id}", response_model=dict)
async def submit_csat(
    conversation_id: UUID,
    payload: CSATSubmission,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Submit a CSAT rating for a resolved/closed conversation.

    Rules: the conversation must exist (404), be resolved or closed (400),
    and not already have a rating (409 — one rating per conversation).
    """
    conversation = await _get_conversation(conversation_id, db)

    if conversation.status not in RATEABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="CSAT can only be submitted for resolved or closed conversations",
        )

    if _existing_csat(conversation):
        raise HTTPException(status_code=409, detail="This conversation has already been rated")

    metadata = dict(conversation.metadata_ or {})
    metadata["csat"] = {
        "score": payload.score,
        "comment": payload.comment,
        "rated_at": datetime.now(tz=UTC).isoformat(),
    }
    conversation.metadata_ = metadata

    await db.commit()

    logger.info(
        "CSAT submitted",
        conversation_id=str(conversation_id),
        score=payload.score,
        has_comment=payload.comment is not None,
    )

    return {
        "success": True,
        "conversation_id": str(conversation_id),
        "score": payload.score,
    }
