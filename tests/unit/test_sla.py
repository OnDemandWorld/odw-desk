"""
ODW.ai Desk — Unit Tests for SLA Timing (F6)

Covers SLAPolicy construction, SLAService.evaluate (ok / first-response breach /
resolution breach), escalate (sets escalated state via the real state machine),
and scan_due_conversations (escalates only breached conversations).

No live DB is needed: a lightweight fake session backs the ConversationManager.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from desk.conversations.state_machine import ConversationStatus
from desk.models.conversation import Conversation
from desk.models.message import Message
from desk.sla.checker import scan_due_conversations
from desk.sla.policy import SLAPolicy
from desk.sla.service import SLAService, SLAStatus

POLICY = SLAPolicy(first_response_minutes=60, resolution_minutes=480)
CREATED = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class _FakeResult:
    """Minimal stand-in for a SQLAlchemy result."""

    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    """Minimal async session: execute() returns canned rows, flush() is a no-op."""

    def __init__(self, rows):
        self._rows = rows
        self.flush_count = 0

    async def execute(self, _stmt):
        return _FakeResult(self._rows)

    async def flush(self):
        self.flush_count += 1


def _conversation(status="active", created_at=CREATED, messages=None, **sla_fields):
    conv = Conversation(
        id=uuid4(), status=status, channel="whatsapp", created_at=created_at
    )
    for key, value in sla_fields.items():
        setattr(conv, key, value)
    conv.messages = messages or []
    return conv


def _ai_response(at: datetime) -> Message:
    return Message(sender_type="ai", content="reply", created_at=at)


class TestSLAPolicy:
    def test_from_settings_derives_minutes(self, monkeypatch):
        monkeypatch.setenv("SLA_FIRST_RESPONSE_MINUTES", "15")
        monkeypatch.setenv("SLA_RESOLUTION_HOURS", "2")
        from desk.config import get_settings

        get_settings.cache_clear()
        try:
            policy = SLAPolicy.from_settings()
        finally:
            get_settings.cache_clear()
        assert policy.first_response_minutes == 15
        assert policy.resolution_minutes == 120


class TestSLAEvaluate:
    def setup_method(self):
        self.service = SLAService(_FakeDB([]), policy=POLICY)

    def test_ok_when_within_both_thresholds(self):
        conv = _conversation()
        now = CREATED + timedelta(minutes=30)
        assert self.service.evaluate(conv, now) is SLAStatus.OK

    def test_breached_first_response_when_no_reply_past_deadline(self):
        conv = _conversation()  # no ai/agent message
        now = CREATED + timedelta(minutes=120)  # past 60-min first-response
        assert self.service.evaluate(conv, now) is SLAStatus.BREACHED_FIRST_RESPONSE

    def test_breached_resolution_when_replied_but_unresolved_past_deadline(self):
        conv = _conversation(messages=[_ai_response(CREATED + timedelta(minutes=10))])
        now = CREATED + timedelta(minutes=500)  # past 480-min resolution
        assert self.service.evaluate(conv, now) is SLAStatus.BREACHED_RESOLUTION

    def test_first_response_satisfied_within_resolution_window_is_ok(self):
        conv = _conversation(messages=[_ai_response(CREATED + timedelta(minutes=10))])
        now = CREATED + timedelta(minutes=120)  # past first-response, within resolution
        assert self.service.evaluate(conv, now) is SLAStatus.OK

    def test_resolved_conversation_is_ok_even_if_old(self):
        conv = _conversation(status="resolved")
        now = CREATED + timedelta(minutes=10_000)
        assert self.service.evaluate(conv, now) is SLAStatus.OK

    def test_explicit_due_field_is_honoured(self):
        # Explicit deadline earlier than the policy-derived one -> breach.
        conv = _conversation(sla_first_response_due=CREATED + timedelta(minutes=5))
        now = CREATED + timedelta(minutes=10)
        assert self.service.evaluate(conv, now) is SLAStatus.BREACHED_FIRST_RESPONSE


class TestSLAEscalate:
    async def test_escalate_sets_escalated_state(self):
        conv = _conversation()  # active, breached
        db = _FakeDB([conv])
        service = SLAService(db, policy=POLICY)

        result = await service.escalate(conv.id, "SLA first-response breach")

        assert result is True
        assert conv.status == ConversationStatus.ESCALATED
        assert conv.metadata_["last_status_change_reason"] == "SLA first-response breach"
        assert db.flush_count >= 1

    async def test_escalate_skips_already_escalated(self):
        conv = _conversation(status="escalated")
        service = SLAService(_FakeDB([conv]), policy=POLICY)
        assert await service.escalate(conv.id, "again") is False

    async def test_escalate_skips_invalid_transition(self):
        conv = _conversation(status="new")  # new -> escalated is invalid
        service = SLAService(_FakeDB([conv]), policy=POLICY)
        assert await service.escalate(conv.id, "breach") is False
        assert conv.status == ConversationStatus.NEW

    async def test_escalate_missing_conversation_returns_false(self):
        service = SLAService(_FakeDB([]), policy=POLICY)
        assert await service.escalate("00000000-0000-0000-0000-000000000000", "x") is False

    async def test_escalate_publishes_breach_event_best_effort(self):
        conv = _conversation()
        published = []

        class _Bus:
            async def publish(self, stream, event):
                published.append((stream, event))
                return "msg-1"

        service = SLAService(_FakeDB([conv]), policy=POLICY, event_bus=_Bus())
        assert await service.escalate(conv.id, "breach") is True
        assert published and published[0][0] == "sla.breach"
        assert published[0][1]["conversation_id"] == str(conv.id)
        assert published[0][1]["sla_type"] == "first_response"


class TestScanDueConversations:
    async def test_escalates_only_breached_conversations(self):
        now = datetime.now(tz=UTC)
        # Old, never replied -> first-response breach relative to the scan clock.
        breached = _conversation(created_at=now - timedelta(days=2))
        # Recent and already replied -> within both SLA windows.
        ok = _conversation(created_at=now - timedelta(minutes=1))
        ok.messages = [_ai_response(now - timedelta(seconds=30))]

        db = _FakeDB([breached, ok])
        service = SLAService(db, policy=POLICY)

        # Route per-id lookups to the right object (fake DB returns all rows).
        by_id = {str(c.id): c for c in (breached, ok)}

        async def _get(cid):
            return by_id.get(str(cid))

        service.manager.get_conversation_by_id = _get

        summary = await scan_due_conversations(db, service=service)

        assert summary["scanned"] == 2
        assert summary["breached"] == 1
        assert summary["escalated"] == 1
        assert breached.status == ConversationStatus.ESCALATED
        assert ok.status == ConversationStatus.ACTIVE
