"""
ODW.ai Desk — Unit Tests for the GDPR Compliance Service (F-Desk-1, DB1-DB4)

Uses a mocked async DB session (matching the existing mock-based unit-test
style — no real database) with real model instances so anonymize/hard-delete
mutations are observable. The tamper-evident audit writer is exercised for DB1
and mocked where the test focuses on export/delete semantics.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from desk.compliance.engine import ComplianceEngine
from desk.compliance.service import ComplianceService
from desk.models.audit_log import AuditLog
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message


def _result(scalar=None, items=None, rowcount=None):
    """Build a mock SQLAlchemy result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = items if items is not None else []
    result.rowcount = rowcount
    return result


def _mock_db(execute_results):
    """Build a mock async session whose execute() yields the given results in order."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()  # AsyncSession.delete is a coroutine
    db.add = MagicMock()
    return db


def _customer():
    customer = Customer(
        id=uuid4(),
        display_name="Alice Example",
        channel_identifiers={"whatsapp": "+15551234567"},
        metadata_={"tier": "gold"},
    )
    customer.created_at = datetime(2026, 1, 1, 10, 0, 0)
    customer.updated_at = datetime(2026, 1, 2, 10, 0, 0)
    return customer


def _conversation(customer_id):
    conv = Conversation(
        id=uuid4(),
        customer_id=customer_id,
        channel="whatsapp",
        channel_conversation_id="+15551234567",
        status="active",
    )
    conv.created_at = datetime(2026, 1, 3, 10, 0, 0)
    return conv


def _message(conversation_id, content, sender_type="customer"):
    msg = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        sender_type=sender_type,
        sender_id="+15551234567",
        content=content,
        metadata_={"channel": "whatsapp"},
        pii_detected=False,
    )
    msg.created_at = datetime(2026, 1, 3, 10, 1, 0)
    return msg


@pytest.fixture
def mock_redis():
    """Best-effort cache cleanup runs against a mock Redis (no network)."""
    with patch("desk.compliance.service.get_redis_manager") as patched:
        manager = MagicMock()
        client = MagicMock()
        client.scan = AsyncMock(return_value=(0, []))
        client.delete = AsyncMock()
        manager.connect = AsyncMock(return_value=client)
        manager.settings.redis_prefix = "desk:"
        patched.return_value = manager
        yield client


class TestExportCustomerData:
    async def test_export_aggregates_profile_conversations_messages(self):
        customer = _customer()
        conv = _conversation(customer.id)
        msg1 = _message(conv.id, "Hello")
        msg2 = _message(conv.id, "Hi there", sender_type="ai")

        db = _mock_db(
            [
                _result(scalar=customer),  # _get_customer
                _result(items=[conv]),  # _get_conversations
                _result(items=[msg1, msg2]),  # _get_messages(conv)
            ]
        )

        with patch.object(ComplianceEngine, "log_audit_event", new_callable=AsyncMock) as audit:
            service = ComplianceService(db)
            result = await service.export_customer_data(customer.id, actor_id="admin-1")

        # Profile section
        assert result["profile"]["display_name"] == "Alice Example"
        assert result["profile"]["channel_identifiers"] == {"whatsapp": "+15551234567"}
        # Conversations + nested messages
        assert result["conversation_count"] == 1
        assert len(result["conversations"]) == 1
        messages = result["conversations"][0]["messages"]
        assert [m["content"] for m in messages] == ["Hello", "Hi there"]
        # Audit written + committed
        audit.assert_awaited_once()
        assert audit.await_args.kwargs["action"] == "export"
        db.commit.assert_awaited()

    async def test_export_missing_customer_raises(self):
        db = _mock_db([_result(scalar=None)])
        service = ComplianceService(db)
        with pytest.raises(ValueError):
            await service.export_customer_data(uuid4())


class TestDeleteCustomerData:
    async def test_anonymize_replaces_pii_and_keeps_structure(self, mock_redis):
        customer = _customer()
        conv = _conversation(customer.id)
        msg1 = _message(conv.id, "My number is +15551234567")
        msg2 = _message(conv.id, "Thanks!", sender_type="ai")

        db = _mock_db(
            [
                _result(scalar=customer),  # _get_customer
                _result(items=[conv]),  # _get_conversations
                _result(items=[msg1, msg2]),  # _get_messages(conv) in _anonymize
            ]
        )

        with patch.object(ComplianceEngine, "log_audit_event", new_callable=AsyncMock) as audit:
            service = ComplianceService(db)
            result = await service.delete_customer_data(
                customer.id, mode="anonymize", actor_id="admin-1", reason="gdpr-request"
            )

        # Customer PII anonymized, structure (identifier keys) preserved
        assert customer.display_name == "[anonymized]"
        assert customer.channel_identifiers == {"whatsapp": "redacted"}
        assert customer.metadata_ == {}
        # Messages anonymized
        assert msg1.content == "[deleted]"
        assert msg1.sender_id is None
        assert msg2.content == "[deleted]"
        # Nothing hard-deleted
        db.delete.assert_not_called()
        # Summary + audit
        assert result["mode"] == "anonymize"
        assert result["anonymized_messages"] == 2
        assert result["anonymized_conversations"] == 1
        audit.assert_awaited_once()
        assert audit.await_args.kwargs["details"]["mode"] == "anonymize"
        db.commit.assert_awaited()

    async def test_anonymize_is_the_default_mode(self, mock_redis):
        customer = _customer()
        db = _mock_db([_result(scalar=customer), _result(items=[])])

        with patch.object(ComplianceEngine, "log_audit_event", new_callable=AsyncMock):
            service = ComplianceService(db)
            result = await service.delete_customer_data(customer.id)

        assert result["mode"] == "anonymize"

    async def test_hard_delete_removes_messages_conversations_customer(self, mock_redis):
        customer = _customer()
        conv = _conversation(customer.id)

        db = _mock_db(
            [
                _result(scalar=customer),  # _get_customer
                _result(items=[conv]),  # _get_conversations
                _result(rowcount=2),  # delete(Message) for conv
            ]
        )

        with patch.object(ComplianceEngine, "log_audit_event", new_callable=AsyncMock) as audit:
            service = ComplianceService(db)
            result = await service.delete_customer_data(
                customer.id, mode="hard", actor_id="admin-1", reason="erasure"
            )

        # Conversation and customer deleted
        deleted_targets = {call.args[0] for call in db.delete.call_args_list}
        assert conv in deleted_targets
        assert customer in deleted_targets
        assert result["mode"] == "hard"
        assert result["deleted_conversations"] == 1
        assert result["deleted_messages"] == 2
        audit.assert_awaited_once()
        assert audit.await_args.kwargs["details"]["mode"] == "hard"
        db.commit.assert_awaited()

    async def test_invalid_mode_raises(self):
        db = _mock_db([])
        service = ComplianceService(db)
        with pytest.raises(ValueError):
            await service.delete_customer_data(uuid4(), mode="purge")

    async def test_missing_customer_raises(self):
        db = _mock_db([_result(scalar=None)])
        service = ComplianceService(db)
        with pytest.raises(ValueError):
            await service.delete_customer_data(uuid4(), mode="hard")


class TestAuditWriter:
    """DB1 — the reused tamper-evident audit writer persists an AuditLog."""

    async def test_log_audit_event_writes_hashed_record(self):
        db = _mock_db([_result(scalar=None)])  # no prior log -> genesis hash

        engine = ComplianceEngine(db)
        record = await engine.log_audit_event(
            action="export",
            actor_id="system",
            actor_type="admin",
            resource_type="customer",
            resource_id=str(uuid4()),
            details={"conversation_count": 1},
        )

        assert isinstance(record, AuditLog)
        assert record.previous_hash == "0" * 64
        assert len(record.hash) == 64
        db.add.assert_called_once_with(record)
        db.flush.assert_awaited()
