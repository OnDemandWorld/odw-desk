"""
ODW.ai Desk — GDPR Compliance Service (F-Desk-1)

Real implementation of the GDPR data-portability and right-to-erasure flows
that replace the V1.0 "log-only" stubs in ``desk.admin.api``.

- ``export_customer_data`` aggregates a customer's profile + conversations +
  messages into a machine-readable dict (GDPR Article 20).
- ``delete_customer_data`` erases a customer either by ``anonymize`` (default,
  replaces PII with placeholders while keeping conversation structure) or
  ``hard`` (deletes messages/conversations/customer) — GDPR Article 17.

Every operation writes a tamper-evident audit record by reusing the existing
``desk.models.audit_log.AuditLog`` store via ``ComplianceEngine.log_audit_event``
(DB1 — existing audit table/model reused, no new table introduced).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.compliance.engine import ComplianceEngine
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message
from desk.utils.redis_client import get_redis_manager

logger = structlog.get_logger()

# Placeholder values used by the anonymize strategy. Conversation/message
# structure is preserved; only personally identifiable content is replaced.
ANONYMIZED_DISPLAY_NAME = "[anonymized]"
ANONYMIZED_CONTENT = "[deleted]"
ANONYMIZED_IDENTIFIER = "redacted"

VALID_DELETE_MODES = ("anonymize", "hard")


class ComplianceService:
    """
    GDPR compliance service operating on an async database session.

    Composes the existing :class:`ComplianceEngine` purely to reuse its
    tamper-evident audit-log writer; export/delete semantics live here.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._engine = ComplianceEngine(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_customer(self, customer_id: UUID) -> Customer | None:
        result = await self.db.execute(select(Customer).where(Customer.id == customer_id))
        return result.scalar_one_or_none()

    async def _get_conversations(self, customer_id: UUID) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.created_at.asc())
        )
        return list(result.scalars().all())

    async def _get_messages(self, conversation_id: UUID) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def _write_audit(
        self,
        action: str,
        customer_id: UUID,
        actor_id: str,
        details: dict[str, Any],
    ) -> None:
        """Write a compliance audit record (best-effort hash-chained)."""
        await self._engine.log_audit_event(
            action=action,
            actor_id=actor_id,
            actor_type="admin",
            resource_type="customer",
            resource_id=str(customer_id),
            details=details,
        )

    # ------------------------------------------------------------------
    # Export (GDPR Article 20 — right to data portability)
    # ------------------------------------------------------------------

    async def export_customer_data(
        self,
        customer_id: UUID,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """
        Aggregate all stored data for a customer into a machine-readable dict.

        Returns:
            ``{"customer_id", "profile", "conversations", "conversation_count",
            "exported_at"}`` where each conversation embeds its messages.

        Raises:
            ValueError: when the customer does not exist.
        """
        customer = await self._get_customer(customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")

        conversations = await self._get_conversations(customer_id)

        profile = {
            "id": str(customer.id),
            "display_name": customer.display_name,
            "channel_identifiers": customer.channel_identifiers,
            "metadata": customer.metadata_,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
        }

        conversation_payload: list[dict[str, Any]] = []
        total_messages = 0
        for conv in conversations:
            messages = await self._get_messages(conv.id)
            total_messages += len(messages)
            conversation_payload.append(
                {
                    "id": str(conv.id),
                    "channel": conv.channel,
                    "channel_conversation_id": conv.channel_conversation_id,
                    "status": conv.status,
                    "created_at": conv.created_at.isoformat() if conv.created_at else None,
                    "messages": [
                        {
                            "id": str(msg.id),
                            "sender_type": msg.sender_type,
                            "sender_id": msg.sender_id,
                            "content": msg.content,
                            "metadata": msg.metadata_,
                            "pii_detected": msg.pii_detected,
                            "created_at": msg.created_at.isoformat() if msg.created_at else None,
                        }
                        for msg in messages
                    ],
                }
            )

        await self._write_audit(
            action="export",
            customer_id=customer_id,
            actor_id=actor_id,
            details={
                "conversation_count": len(conversations),
                "message_count": total_messages,
            },
        )
        await self.db.commit()

        logger.info(
            "Customer data exported",
            customer_id=str(customer_id),
            conversations=len(conversations),
            messages=total_messages,
        )

        return {
            "customer_id": str(customer_id),
            "profile": profile,
            "conversations": conversation_payload,
            "conversation_count": len(conversations),
            "exported_at": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Deletion (GDPR Article 17 — right to erasure)
    # ------------------------------------------------------------------

    async def delete_customer_data(
        self,
        customer_id: UUID,
        mode: str = "anonymize",
        actor_id: str = "system",
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Erase a customer's data using the given strategy (transactional).

        Args:
            customer_id: Target customer.
            mode: ``"anonymize"`` (default) replaces PII with placeholders while
                keeping conversation structure; ``"hard"`` deletes messages,
                conversations, and the customer record.
            actor_id: Actor requesting the erasure (for audit).
            reason: Optional human-readable reason (for audit).

        Returns:
            Deletion summary including ``mode`` and per-strategy counters.

        Raises:
            ValueError: when mode is invalid or the customer does not exist.
        """
        if mode not in VALID_DELETE_MODES:
            raise ValueError(f"Invalid delete mode '{mode}'; expected one of {VALID_DELETE_MODES}")

        customer = await self._get_customer(customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")

        conversations = await self._get_conversations(customer_id)

        if mode == "anonymize":
            summary = await self._anonymize(customer, conversations)
        else:
            summary = await self._hard_delete(customer, conversations)

        await self._write_audit(
            action="delete",
            customer_id=customer_id,
            actor_id=actor_id,
            details={"mode": mode, "reason": reason, **summary},
        )
        await self.db.commit()

        # Best-effort cache cleanup — never blocks or fails the erasure.
        await self._cleanup_cache(customer_id)

        logger.info(
            "Customer data deleted",
            customer_id=str(customer_id),
            mode=mode,
            reason=reason,
            **summary,
        )

        return {"customer_id": str(customer_id), "mode": mode, **summary}

    async def _anonymize(
        self,
        customer: Customer,
        conversations: list[Conversation],
    ) -> dict[str, int]:
        """Replace PII with placeholders, preserving conversation structure."""
        customer.display_name = ANONYMIZED_DISPLAY_NAME
        customer.channel_identifiers = dict.fromkeys(
            customer.channel_identifiers or {}, ANONYMIZED_IDENTIFIER
        )
        customer.metadata_ = {}

        anonymized_messages = 0
        for conv in conversations:
            messages = await self._get_messages(conv.id)
            for msg in messages:
                msg.content = ANONYMIZED_CONTENT
                msg.content_redacted = None
                msg.sender_id = None
                msg.metadata_ = {}
                msg.pii_types = []
                anonymized_messages += 1

        await self.db.flush()
        return {
            "anonymized_conversations": len(conversations),
            "anonymized_messages": anonymized_messages,
        }

    async def _hard_delete(
        self,
        customer: Customer,
        conversations: list[Conversation],
    ) -> dict[str, int]:
        """Delete messages, conversations, and the customer record."""
        deleted_messages = 0
        for conv in conversations:
            result = await self.db.execute(
                delete(Message).where(Message.conversation_id == conv.id)
            )
            deleted_messages += result.rowcount or 0
            await self.db.delete(conv)

        await self.db.delete(customer)
        await self.db.flush()
        return {
            "deleted_conversations": len(conversations),
            "deleted_messages": deleted_messages,
        }

    async def _cleanup_cache(self, customer_id: UUID) -> None:
        """Best-effort removal of cached references to the erased customer."""
        try:
            manager = get_redis_manager()
            client = await manager.connect()
            pattern = f"{manager.settings.redis_prefix}*{customer_id}*"
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Cache cleanup after erasure failed (best-effort)",
                customer_id=str(customer_id),
                error=str(exc),
            )
