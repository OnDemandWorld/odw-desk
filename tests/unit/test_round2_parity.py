"""
ODW.ai Desk — Unit Tests for Round-2 Chatwoot-Parity Features

Covers:
- Inbox enrichment: X-Total-Count header, unread counts, last-message
  preview, customer name; FSM-validated status updates; mark-read.
- Reports overview: counts by status, unassigned queue, message volume,
  AI deflection rate, avg confidence, first-response time, CSAT aggregate.
- Public CSAT API: submit/get lifecycle (404/400/409/200).

Mock-based style matching the existing unit suite (no real database).
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from desk.config import get_settings
from desk.dependencies import get_db
from desk.main import app
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message
from desk.router.customer_resolver import CustomerResolver


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    get_settings.cache_clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _override_db(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return db


def _mock_db(*results):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _mock_db_always(result):
    """Session whose execute returns the same result on every call."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _conversation(status="active", metadata=None):
    conv_id, cust_id = uuid4(), uuid4()
    now = datetime.now(tz=UTC)
    conv = Conversation(
        id=conv_id,
        customer_id=cust_id,
        channel="whatsapp",
        channel_conversation_id="wamid.test123",
        status=status,
        ai_enabled=True,
        metadata_=metadata,
    )
    conv.customer = Customer(
        id=cust_id, display_name="Alice", channel_identifiers={"whatsapp": "+15550001111"}
    )
    conv.assigned_agent = None
    conv.created_at = now - timedelta(hours=1)
    conv.updated_at = now
    return conv


class TestInboxEnrichment:
    """X-Total-Count, unread counts, last-message preview, customer name."""

    def test_list_returns_total_count_header_and_enrichment(self, client):
        conv = _conversation()
        msg = Message(
            id=uuid4(),
            conversation_id=conv.id,
            sender_type="customer",
            content="Where is my order?" + "x" * 200,
            created_at=datetime.now(tz=UTC),
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [conv]
        unread_result = MagicMock()
        unread_result.all.return_value = [(conv.id, 3)]
        last_result = MagicMock()
        last_result.scalars.return_value = [msg]

        _override_db(_mock_db(count_result, data_result, unread_result, last_result))

        response = client.get("/api/v1/agents/conversations")
        assert response.status_code == 200
        assert response.headers["x-total-count"] == "1"

        data = response.json()
        assert len(data) == 1
        item = data[0]
        assert item["customer_name"] == "Alice"
        assert item["unread_count"] == 3
        assert item["last_message"]["sender_type"] == "customer"
        assert item["last_message"]["content"].endswith("…")
        assert len(item["last_message"]["content"]) == 141

    def test_list_empty_page_sets_zero_header(self, client):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 7
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        _override_db(_mock_db(count_result, data_result))

        response = client.get("/api/v1/agents/conversations?offset=100")
        assert response.status_code == 200
        assert response.headers["x-total-count"] == "7"
        assert response.json() == []


class TestConversationStatusEndpoint:
    """FSM-validated status updates with websocket broadcast."""

    def _patch_broadcast(self, monkeypatch):
        broadcast = AsyncMock()
        monkeypatch.setattr(
            "desk.agents.inbox_api.broadcast_conversation_update", broadcast
        )
        return broadcast

    def test_valid_transition_updates_and_broadcasts(self, client, monkeypatch):
        conv = _conversation(status="active")
        broadcast = self._patch_broadcast(monkeypatch)
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        db = _override_db(_mock_db(result))

        response = client.post(
            f"/api/v1/agents/conversations/{conv.id}/status",
            json={"status": "pending", "reason": "awaiting customer reply"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        assert conv.status == "pending"
        db.commit.assert_awaited_once()
        broadcast.assert_awaited_once()

    def test_invalid_transition_is_400(self, client, monkeypatch):
        conv = _conversation(status="closed")
        self._patch_broadcast(monkeypatch)
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        _override_db(_mock_db(result))

        response = client.post(
            f"/api/v1/agents/conversations/{conv.id}/status",
            json={"status": "active"},
        )

        assert response.status_code == 400
        assert "Invalid transition" in response.json()["detail"]

    def test_unknown_conversation_is_404(self, client):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        _override_db(_mock_db(result))

        response = client.post(
            f"/api/v1/agents/conversations/{uuid4()}/status",
            json={"status": "active"},
        )
        assert response.status_code == 404

    def test_unknown_status_value_is_422(self, client):
        conv = _conversation()
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        _override_db(_mock_db(result))

        response = client.post(
            f"/api/v1/agents/conversations/{conv.id}/status",
            json={"status": "teleported"},
        )
        assert response.status_code == 422


class TestMarkConversationRead:
    """Unread customer messages get a read_at receipt."""

    def test_marks_unread_messages(self, client):
        conv = _conversation()
        exists_result = MagicMock()
        exists_result.scalar_one_or_none.return_value = conv.id
        update_result = MagicMock()
        update_result.rowcount = 3
        db = _override_db(_mock_db(exists_result, update_result))

        response = client.post(f"/api/v1/agents/conversations/{conv.id}/read")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["marked_read"] == 3
        db.commit.assert_awaited_once()

    def test_unknown_conversation_is_404(self, client):
        exists_result = MagicMock()
        exists_result.scalar_one_or_none.return_value = None
        _override_db(_mock_db(exists_result))

        response = client.post(f"/api/v1/agents/conversations/{uuid4()}/read")
        assert response.status_code == 404


class TestCustomerNameEnrichment:
    """Resolver adopts channel profile names for unnamed customers."""

    def _resolver_db(self, existing):
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()
        db.add = MagicMock()
        return db

    async def test_existing_customer_without_name_adopts_profile_name(self):
        customer = Customer(
            channel_identifiers={"whatsapp": "+15559876501"}, display_name=None
        )
        db = self._resolver_db(customer)

        resolved = await CustomerResolver(db).resolve_or_create(
            channel="whatsapp", identifier="+15559876501", display_name="Alice Smoke"
        )

        assert resolved is customer
        assert customer.display_name == "Alice Smoke"
        db.add.assert_not_called()  # updated in place, no duplicate row

    async def test_existing_customer_with_name_is_not_overwritten(self):
        customer = Customer(
            channel_identifiers={"whatsapp": "+15559876501"}, display_name="Agent Set"
        )
        db = self._resolver_db(customer)

        resolved = await CustomerResolver(db).resolve_or_create(
            channel="whatsapp", identifier="+15559876501", display_name="Alice Smoke"
        )

        assert resolved.display_name == "Agent Set"

    async def test_new_customer_created_with_profile_name(self):
        db = self._resolver_db(None)

        customer = await CustomerResolver(db).resolve_or_create(
            channel="whatsapp", identifier="+15559876501", display_name="Alice Smoke"
        )

        assert customer.display_name == "Alice Smoke"
        db.add.assert_called_once()


class TestReportsOverview:
    """Dashboard aggregates over mocked group-by results (call order fixed)."""

    def test_overview_aggregates_all_sections(self, client):
        now = datetime.now(tz=UTC)

        status_result = MagicMock()
        status_result.all.return_value = [("active", 3), ("resolved", 5), ("new", 2)]
        unassigned_result = MagicMock()
        unassigned_result.scalar_one.return_value = 2
        messages_result = MagicMock()
        messages_result.all.return_value = [("customer", 10), ("ai", 8), ("agent", 2)]
        deflection_result = MagicMock()
        deflection_result.all.return_value = [
            SimpleNamespace(has_agent=False, has_ai=True),  # AI-only conversation
            SimpleNamespace(has_agent=True, has_ai=True),   # human-touched
        ]
        confidence_result = MagicMock()
        confidence_result.scalars.return_value.all.return_value = ["0.9", "0.7", None, "junk"]
        frt_result = MagicMock()
        frt_result.all.return_value = [
            SimpleNamespace(first_customer=now, first_response=now + timedelta(seconds=90)),
            SimpleNamespace(first_customer=None, first_response=now),  # skipped
        ]
        csat_result = MagicMock()
        csat_result.all.return_value = [
            ("5", now.isoformat()),                        # in window
            ("1", "2020-01-01T00:00:00+00:00"),            # outside window
            (None, None),                                  # no csat
        ]

        _override_db(
            _mock_db(
                status_result,
                unassigned_result,
                messages_result,
                deflection_result,
                confidence_result,
                frt_result,
                csat_result,
            )
        )

        response = client.get("/api/v1/agents/reports/overview?days=7")

        assert response.status_code == 200
        body = response.json()

        assert body["window"]["days"] == 7
        conversations = body["conversations"]
        assert conversations["total"] == 10
        assert conversations["open"] == 5  # active 3 + new 2
        assert conversations["by_status"]["resolved"] == 5
        assert conversations["unassigned_open"] == 2

        assert body["messages"]["total"] == 20
        assert body["messages"]["by_sender"]["ai"] == 8

        ai = body["ai"]
        assert ai["deflection_rate"] == 0.5
        assert ai["ai_handled_conversations"] == 1
        assert ai["human_handled_conversations"] == 1
        assert ai["avg_confidence"] == 0.8  # junk + None skipped
        assert ai["replies_in_window"] == 8

        assert body["response_time"]["avg_first_response_seconds"] == 90.0
        assert body["response_time"]["conversations_sampled"] == 1

        assert body["csat"]["avg_score"] == 5.0
        assert body["csat"]["ratings_count"] == 1

    def test_overview_handles_empty_data(self, client):
        r_empty_all = MagicMock()
        r_empty_all.all.return_value = []
        r_empty_scalars = MagicMock()
        r_empty_scalars.scalar_one.return_value = 0
        r_conf = MagicMock()
        r_conf.scalars.return_value.all.return_value = []

        _override_db(
            _mock_db(
                r_empty_all,   # status counts
                r_empty_scalars,
                r_empty_all,   # messages by sender
                r_empty_all,   # deflection
                r_conf,        # confidence
                r_empty_all,   # first response
                r_empty_all,   # csat
            )
        )

        response = client.get("/api/v1/agents/reports/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["conversations"]["total"] == 0
        assert body["ai"]["deflection_rate"] is None
        assert body["csat"]["avg_score"] is None

    def test_overview_days_bounds_are_422(self, client):
        response = client.get("/api/v1/agents/reports/overview?days=0")
        assert response.status_code == 422
        response = client.get("/api/v1/agents/reports/overview?days=91")
        assert response.status_code == 422


class TestPublicCSAT:
    """CSAT lifecycle: 404 / 400 (open conversation) / 409 (dup) / 200."""

    def test_unknown_conversation_is_404(self, client):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        _override_db(_mock_db(result))

        response = client.post(
            f"/api/v1/public/csat/{uuid4()}", json={"score": 5}
        )
        assert response.status_code == 404

    def test_open_conversation_is_400(self, client):
        conv = _conversation(status="active")
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        db = _override_db(_mock_db(result))

        response = client.post(
            f"/api/v1/public/csat/{conv.id}", json={"score": 4}
        )
        assert response.status_code == 400
        db.commit.assert_not_awaited()

    def test_submit_and_duplicate(self, client):
        conv = _conversation(status="resolved")
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        db = _override_db(_mock_db_always(result))

        response = client.post(
            f"/api/v1/public/csat/{conv.id}",
            json={"score": 5, "comment": "Great support!"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["score"] == 5
        assert conv.metadata_["csat"]["score"] == 5
        assert conv.metadata_["csat"]["comment"] == "Great support!"
        db.commit.assert_awaited_once()

        # Second submission hits the 409 already-rated guard.
        response = client.post(f"/api/v1/public/csat/{conv.id}", json={"score": 1})
        assert response.status_code == 409

    def test_invalid_score_is_422(self, client):
        conv = _conversation(status="resolved")
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        _override_db(_mock_db(result))

        response = client.post(f"/api/v1/public/csat/{conv.id}", json={"score": 9})
        assert response.status_code == 422

    def test_get_status_lifecycle(self, client):
        unrated = _conversation(status="resolved")
        rated = _conversation(
            status="resolved",
            metadata={"csat": {"score": 4, "comment": None, "rated_at": "2026-08-01T00:00:00+00:00"}},
        )
        active = _conversation(status="active")

        for conv, expected in ((unrated, True), (rated, False), (active, False)):
            result = MagicMock()
            result.scalar_one_or_none.return_value = conv
            _override_db(_mock_db(result))
            response = client.get(f"/api/v1/public/csat/{conv.id}")
            assert response.status_code == 200
            assert response.json()["rateable"] is expected

        # The rated conversation reports its stored payload.
        result = MagicMock()
        result.scalar_one_or_none.return_value = rated
        _override_db(_mock_db(result))
        body = client.get(f"/api/v1/public/csat/{rated.id}").json()
        assert body["already_rated"] is True
        assert body["score"] == 4
