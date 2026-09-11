"""
ODW.ai Desk — Compliance Engine (AGENT-005)

Enforces data retention policies, generates compliance reports,
handles data export/deletion requests (GDPR), and maintains tamper-evident audit log.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.config import get_settings
from desk.models.audit_log import AuditLog
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message

logger = structlog.get_logger()


class ComplianceEngine:
    """
    Compliance Engine for data retention, export, deletion, and audit.

    Implements GDPR requirements and maintains tamper-evident audit trail.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    # ========================================================================
    # Audit Log Management (Tamper-Evident)
    # ========================================================================

    async def log_audit_event(
        self,
        action: str,
        actor_id: str,
        actor_type: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        event_type: str | None = None,
    ) -> AuditLog:
        """
        Log an audit event with hash chain for tamper evidence.

        Args:
            action: Action performed (e.g., "create", "update", "delete")
            actor_id: ID of the actor (user, agent, system)
            actor_type: Type of actor ("user", "agent", "system")
            resource_type: Type of resource affected
            resource_id: ID of the resource
            details: Additional details
            ip_address: IP address of the actor

        Returns:
            Created AuditLog entry
        """
        # Get the latest audit log entry for hash chaining
        query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(1)
        result = await self.db.execute(query)
        latest_log = result.scalar_one_or_none()

        previous_hash = latest_log.hash if latest_log else "0" * 64

        # Coerce the actor to the UUID column type. Free-text actors (e.g. the
        # default "system") cannot bind to the PG UUID column — asyncpg rejects
        # the INSERT and the surrounding GDPR operation would roll back. The
        # raw value is preserved in details so attribution is never lost.
        actor_uuid: UUID | None = None
        try:
            actor_uuid = UUID(str(actor_id))
        except (ValueError, AttributeError, TypeError):
            actor_uuid = None
        details_stored = dict(details or {})
        if actor_uuid is None and actor_id:
            details_stored.setdefault("actor_id_raw", str(actor_id))

        timestamp = datetime.now(tz=UTC)

        # event_type is a NOT NULL column with no default; derive it from the
        # action unless the caller supplies one explicitly.
        resolved_event_type = event_type or {
            "export": "data_access",
            "delete": "data_deletion",
        }.get(action, "data_access")

        # Build the log entry data. Values must serialize exactly as they are
        # stored, so verify_audit_chain re-derives the identical input.
        log_data = {
            "action": action,
            "actor_id": str(actor_uuid) if actor_uuid else None,
            "actor_type": actor_type,
            "event_type": resolved_event_type,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "details": details_stored,
            "ip_address": ip_address,
            "previous_hash": previous_hash,
            "timestamp": timestamp.isoformat(),
        }

        # Calculate hash
        log_json = json.dumps(log_data, sort_keys=True, default=str)
        current_hash = hashlib.sha256(log_json.encode()).hexdigest()

        # Create audit log entry
        audit_log = AuditLog(
            action=action,
            actor_id=actor_uuid,
            actor_type=actor_type,
            event_type=resolved_event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details_stored,
            ip_address=ip_address,
            previous_hash=previous_hash,
            hash=current_hash,
            timestamp=timestamp,
        )

        self.db.add(audit_log)
        await self.db.flush()

        logger.info(
            "Audit event logged",
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        return audit_log

    async def verify_audit_chain(self) -> dict[str, Any]:
        """
        Verify the integrity of the audit log hash chain.

        Returns:
            Verification result with status and any issues found
        """
        query = select(AuditLog).order_by(AuditLog.timestamp.asc())
        result = await self.db.execute(query)
        logs = result.scalars().all()

        issues = []
        previous_hash = "0" * 64

        for log in logs:
            # Verify previous hash matches
            if log.previous_hash != previous_hash:
                issues.append({
                    "log_id": str(log.id),
                    "issue": "previous_hash_mismatch",
                    "expected": previous_hash,
                    "actual": log.previous_hash,
                })

            # Verify current hash (serialization mirrors log_audit_event)
            log_data = {
                "action": log.action,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "actor_type": log.actor_type,
                "event_type": log.event_type,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id),
                "details": log.details,
                "ip_address": log.ip_address,
                "previous_hash": log.previous_hash,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            log_json = json.dumps(log_data, sort_keys=True, default=str)
            expected_hash = hashlib.sha256(log_json.encode()).hexdigest()

            if log.hash != expected_hash:
                issues.append({
                    "log_id": str(log.id),
                    "issue": "hash_mismatch",
                    "expected": expected_hash,
                    "actual": log.hash,
                })

            previous_hash = log.hash

        return {
            "valid": len(issues) == 0,
            "total_logs": len(logs),
            "issues": issues,
        }

    # ========================================================================
    # Data Retention Management
    # ========================================================================

    async def enforce_retention_policy(self) -> dict[str, Any]:
        """
        Enforce data retention policy by deleting old conversations.

        Returns:
            Summary of deleted data
        """
        retention_days = self.settings.data_retention_days
        cutoff_date = datetime.now(tz=UTC) - timedelta(days=retention_days)

        # Find conversations older than retention period
        query = select(Conversation).where(Conversation.updated_at < cutoff_date)
        result = await self.db.execute(query)
        old_conversations = result.scalars().all()

        deleted_count = 0
        for conversation in old_conversations:
            # Delete all messages in the conversation
            msg_query = delete(Message).where(Message.conversation_id == conversation.id)
            await self.db.execute(msg_query)

            # Delete the conversation
            await self.db.delete(conversation)
            deleted_count += 1

            # Log deletion
            await self.log_audit_event(
                action="delete",
                actor_id="system",
                actor_type="system",
                resource_type="conversation",
                resource_id=str(conversation.id),
                details={"reason": "retention_policy", "cutoff_date": cutoff_date.isoformat()},
            )

        await self.db.commit()

        logger.info("Retention policy enforced", deleted_conversations=deleted_count)

        return {
            "deleted_conversations": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
            "retention_days": retention_days,
        }

    # ========================================================================
    # Data Export (GDPR Article 20)
    # ========================================================================

    async def export_customer_data(self, customer_id: UUID) -> dict[str, Any]:
        """
        Export all data for a customer (GDPR right to data portability).

        Args:
            customer_id: Customer ID

        Returns:
            Export data structure
        """
        # Get customer
        customer_query = select(Customer).where(Customer.id == customer_id)
        customer_result = await self.db.execute(customer_query)
        customer = customer_result.scalar_one_or_none()

        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # Get all conversations for this customer
        conv_query = (
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.created_at.asc())
        )
        conv_result = await self.db.execute(conv_query)
        conversations = conv_result.scalars().all()

        # Build export structure
        export_data: dict[str, Any] = {
            "customer": {
                "id": str(customer.id),
                "channel_identifiers": customer.channel_identifiers,
                "metadata": customer.metadata_,
                "created_at": customer.created_at.isoformat() if customer.created_at else None,
            },
            "conversations": [],
        }

        for conv in conversations:
            # Get messages for this conversation
            msg_query = (
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at.asc())
            )
            msg_result = await self.db.execute(msg_query)
            messages = msg_result.scalars().all()

            export_data["conversations"].append({
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
                        "content_redacted": msg.content_redacted,
                        "pii_detected": msg.pii_detected,
                        "pii_types": msg.pii_types,
                        "metadata": msg.metadata_,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    }
                    for msg in messages
                ],
            })

        # Log export
        await self.log_audit_event(
            action="export",
            actor_id="system",
            actor_type="system",
            resource_type="customer",
            resource_id=str(customer_id),
            details={"conversation_count": len(conversations)},
        )

        await self.db.commit()

        logger.info(
            "Customer data exported",
            customer_id=str(customer_id),
            conversations=len(conversations),
        )

        return export_data

    # ========================================================================
    # Data Deletion (GDPR Article 17)
    # ========================================================================

    async def delete_customer_data(
        self,
        customer_id: UUID,
        reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """
        Delete all data for a customer (GDPR right to erasure).

        Args:
            customer_id: Customer ID
            reason: Deletion reason
            actor_id: Actor requesting deletion

        Returns:
            Deletion summary
        """
        # Get customer
        customer_query = select(Customer).where(Customer.id == customer_id)
        customer_result = await self.db.execute(customer_query)
        customer = customer_result.scalar_one_or_none()

        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # Get all conversations for this customer
        conv_query = select(Conversation).where(Conversation.customer_id == customer_id)
        conv_result = await self.db.execute(conv_query)
        conversations = conv_result.scalars().all()

        deleted_messages = 0
        deleted_conversations = len(conversations)

        # Delete all messages and conversations
        for conv in conversations:
            msg_query = delete(Message).where(Message.conversation_id == conv.id)
            msg_result = await self.db.execute(msg_query)
            deleted_messages += msg_result.rowcount  # type: ignore

            await self.db.delete(conv)

        # Delete customer
        await self.db.delete(customer)

        # Log deletion
        await self.log_audit_event(
            action="delete",
            actor_id=actor_id,
            actor_type="user",
            resource_type="customer",
            resource_id=str(customer_id),
            details={
                "reason": reason,
                "deleted_conversations": deleted_conversations,
                "deleted_messages": deleted_messages,
            },
        )

        await self.db.commit()

        logger.info(
            "Customer data deleted",
            customer_id=str(customer_id),
            reason=reason,
            conversations=deleted_conversations,
            messages=deleted_messages,
        )

        return {
            "customer_id": str(customer_id),
            "deleted_conversations": deleted_conversations,
            "deleted_messages": deleted_messages,
            "reason": reason,
        }
