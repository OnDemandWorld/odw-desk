"""
ODW.ai Desk — Reports & Overview API (Chatwoot-parity, round 2)

Dashboard aggregates: conversation counts by status, message volume by
sender, AI performance (deflection rate + average confidence — the
AI-support differentiator vs Chatwoot), first-response time, and CSAT.

Windowed metrics (messages, AI, response time, CSAT) aggregate over the
``days`` parameter; conversation counts reflect current state (they are
stock, not flow, measures).
"""

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.dependencies import get_db
from desk.models.conversation import Conversation
from desk.models.message import Message

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/agents/reports", tags=["Reports"])

OPEN_STATUSES = ("new", "active", "pending", "escalated")


def _safe_float(value: str | None) -> float | None:
    """Parse a JSON-text numeric value, tolerating junk stored in metadata."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@router.get("/overview", response_model=dict)
async def reports_overview(
    days: int = Query(7, ge=1, le=90, description="Aggregation window in days"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Chatwoot-style overview dashboard payload.

    Accessible to agents and admins (agent_guard). All aggregates are single
    SQL group-bys; nothing loads unbounded row sets into Python except the
    small confidence/CSAT extracts.
    """
    since = datetime.now(tz=UTC) - timedelta(days=days)

    # 1. Conversations by current status (stock measure, all time).
    status_rows = (
        await db.execute(select(Conversation.status, func.count()).group_by(Conversation.status))
    ).all()
    status_counts: dict[str, int] = dict(status_rows)
    total_conversations = sum(status_counts.values())
    open_conversations = sum(status_counts.get(s, 0) for s in OPEN_STATUSES)

    # 2. Unassigned conversations still in an open status (agent queue depth).
    unassigned_open = (
        await db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.assigned_agent_id.is_(None), Conversation.status.in_(OPEN_STATUSES))
        )
    ).scalar_one()

    # 3. Message volume by sender in the window (flow measure).
    message_rows = (
        await db.execute(
            select(Message.sender_type, func.count())
            .where(Message.created_at >= since)
            .group_by(Message.sender_type)
        )
    ).all()
    messages_by_sender: dict[str, int] = dict(message_rows)

    # 4. AI deflection: conversations active in the window that AI handled
    #    end-to-end (>=1 AI reply, no human-agent message) vs human-touched.
    deflection_rows = (
        await db.execute(
            select(
                Message.conversation_id,
                func.bool_or(Message.sender_type == "agent").label("has_agent"),
                func.bool_or(Message.sender_type == "ai").label("has_ai"),
            )
            .where(Message.created_at >= since)
            .group_by(Message.conversation_id)
        )
    ).all()
    ai_handled = sum(1 for row in deflection_rows if row.has_ai and not row.has_agent)
    human_handled = sum(1 for row in deflection_rows if row.has_agent)
    handled_total = ai_handled + human_handled
    deflection_rate = round(ai_handled / handled_total, 4) if handled_total else None

    # 5. Average AI confidence in the window (stored in message metadata).
    confidence_values = (
        (
            await db.execute(
                select(Message.metadata_["confidence"].astext).where(
                    Message.created_at >= since, Message.sender_type == "ai"
                )
            )
        )
        .scalars()
        .all()
    )
    confidences = [c for c in (_safe_float(v) for v in confidence_values) if c is not None]
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None

    # 6. Average first-response time for conversations created in the window:
    #    first human/AI reply minus first customer message (aggregate FILTER).
    frt_rows = (
        await db.execute(
            select(
                func.min(Message.created_at)
                .filter(Message.sender_type == "customer")
                .label("first_customer"),
                func.min(Message.created_at)
                .filter(Message.sender_type.in_(("ai", "agent")))
                .label("first_response"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.created_at >= since)
            .group_by(Message.conversation_id)
        )
    ).all()
    first_response_durations = [
        (row.first_response - row.first_customer).total_seconds()
        for row in frt_rows
        if row.first_customer is not None and row.first_response is not None
    ]
    first_response_durations = [d for d in first_response_durations if d >= 0]
    avg_first_response = (
        round(sum(first_response_durations) / len(first_response_durations), 2)
        if first_response_durations
        else None
    )

    # 7. CSAT (submitted via /api/v1/public/csat, stored in metadata) in window.
    csat_rows = (
        await db.execute(
            select(
                Conversation.metadata_["csat"]["score"].astext,
                Conversation.metadata_["csat"]["rated_at"].astext,
            )
        )
    ).all()
    windowed_scores = []
    for score_text, rated_at_text in csat_rows:
        rated_at = _parse_iso(rated_at_text)
        if rated_at is not None and rated_at >= since:
            score = _safe_float(score_text)
            if score is not None:
                windowed_scores.append(score)
    avg_csat = round(sum(windowed_scores) / len(windowed_scores), 2) if windowed_scores else None

    return {
        "window": {"days": days, "since": since.isoformat()},
        "conversations": {
            "total": total_conversations,
            "open": open_conversations,
            "by_status": status_counts,
            "unassigned_open": unassigned_open,
        },
        "messages": {
            "total": sum(messages_by_sender.values()),
            "by_sender": messages_by_sender,
        },
        "ai": {
            "deflection_rate": deflection_rate,
            "ai_handled_conversations": ai_handled,
            "human_handled_conversations": human_handled,
            "avg_confidence": avg_confidence,
            "replies_in_window": messages_by_sender.get("ai", 0),
        },
        "response_time": {
            "avg_first_response_seconds": avg_first_response,
            "conversations_sampled": len(first_response_durations),
        },
        "csat": {
            "avg_score": avg_csat,
            "ratings_count": len(windowed_scores),
        },
    }
