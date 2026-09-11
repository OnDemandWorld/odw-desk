"""
ODW.ai Desk — SLA Checker

Scans active conversations and escalates those in breach of the SLA policy.

This exposes a callable coroutine; scheduling wiring (cron/worker) is an ops
concern and is intentionally out of scope for V1.1.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from desk.agents.websocket import broadcast_escalation
from desk.models.conversation import Conversation
from desk.observability.metrics import ESCALATIONS
from desk.sla.service import ACTIVE_STATUSES, SLAService, SLAStatus

logger = structlog.get_logger()


async def scan_due_conversations(
    db: AsyncSession, service: SLAService | None = None
) -> dict:
    """
    Evaluate active conversations and escalate those in breach.

    Args:
        db: Async database session.
        service: Optional pre-configured SLAService (built from ``db`` if omitted).

    Returns:
        Summary dict: ``{"scanned": int, "breached": int, "escalated": int}``.
    """
    service = service or SLAService(db)

    # Eager-load messages: the SLA evaluation reads the conversation's
    # message timestamps, and a lazy load inside this async context would
    # fail with MissingGreenlet — the scan then never escalates anything.
    result = await db.execute(
        select(Conversation)
        .where(Conversation.status.in_(ACTIVE_STATUSES))
        .options(selectinload(Conversation.messages))
    )
    conversations = result.scalars().all()

    breached = 0
    escalated = 0
    for conversation in conversations:
        status = service.evaluate(conversation)
        if status is SLAStatus.OK:
            continue
        breached += 1
        reason = (
            "SLA resolution breach"
            if status is SLAStatus.BREACHED_RESOLUTION
            else "SLA first-response breach"
        )
        if await service.escalate(conversation.id, reason):
            escalated += 1
            ESCALATIONS.labels(reason="sla_breach").inc()
            # Notify all connected agents — breached conversations are
            # typically unassigned, so subscription-scoped routing would
            # miss them.
            await broadcast_escalation(
                str(conversation.id),
                {
                    "reason": "sla_breach",
                    "breach": status.value,
                    "detail": reason,
                },
            )

    logger.info(
        "SLA scan complete",
        scanned=len(conversations),
        breached=breached,
        escalated=escalated,
    )
    return {"scanned": len(conversations), "breached": breached, "escalated": escalated}
