"""
ODW.ai Desk — Unit Tests for the Compliance Audit Report Export (V1.4 F-3, P1-P2)

P1: ``build_audit_report_query`` applies time-range / actor / action filters.
P2: ``GET /compliance/report`` returns filtered records as JSON or CSV (stdlib
csv only) and is guarded by ``require_role('admin')`` (non-admin -> 403).

The DB session is overridden with a mock (matching the existing mock-based unit
style — no real database).
"""

import csv
import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from desk.admin.api import build_audit_report_query
from desk.config import get_settings
from desk.dependencies import get_db
from desk.main import app
from desk.models.audit_log import AuditLog


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _audit_log(action="delete", actor_id=None, ts=None, event_type="data_deletion"):
    log = AuditLog(
        id=uuid4(),
        event_type=event_type,
        actor_type="admin",
        actor_id=actor_id,
        resource_type="customer",
        resource_id=uuid4(),
        action=action,
        details={"mode": "hard"},
        ip_address="127.0.0.1",
        previous_hash="0" * 64,
        hash="a" * 64,
    )
    log.timestamp = ts or datetime(2026, 1, 1, 12, 0, 0)
    return log


def _override_db(logs):
    """Override the get_db dependency to yield a mock session returning ``logs``."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = logs
    db.execute = AsyncMock(return_value=result)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return db


class TestBuildAuditReportQuery:
    """P1 — the report query applies time-range / actor / action filters."""

    @staticmethod
    def _sql(query) -> str:
        return str(query.compile(compile_kwargs={"literal_binds": True}))

    def test_no_filters_has_no_where_but_orders_and_limits(self):
        sql = self._sql(build_audit_report_query(limit=50))
        assert "ORDER BY audit_logs.timestamp DESC" in sql
        assert "LIMIT" in sql
        assert "WHERE" not in sql

    def test_time_range_filters_on_timestamp(self):
        sql = self._sql(
            build_audit_report_query(
                start=datetime(2026, 1, 1), end=datetime(2026, 2, 1), limit=10
            )
        )
        assert "audit_logs.timestamp >= " in sql
        assert "audit_logs.timestamp <= " in sql

    def test_actor_and_action_filters(self):
        sql = self._sql(build_audit_report_query(actor="admin-1", action="delete"))
        # actor compared as text (actor ids are logged as opaque strings)
        assert "audit_logs.actor_id" in sql
        assert "admin-1" in sql
        assert "audit_logs.action = " in sql
        assert "delete" in sql


class TestComplianceReportEndpoint:
    """P2 — JSON/CSV export, filters, and the admin guard."""

    def test_json_report_returns_records(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        actor = uuid4()
        _override_db([_audit_log(action="delete", actor_id=actor)])

        response = client.get(
            "/api/v1/admin/compliance/report",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["format"] == "json"
        assert body["total"] == 1
        record = body["records"][0]
        assert record["action"] == "delete"
        assert record["actor_id"] == str(actor)
        assert record["hash"] == "a" * 64
        assert record["details"] == {"mode": "hard"}

    def test_csv_report_has_header_and_row(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        _override_db([_audit_log(action="export")])

        response = client.get(
            "/api/v1/admin/compliance/report",
            params={"format": "csv"},
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert len(rows) == 1
        assert rows[0]["action"] == "export"
        assert "attachment" in response.headers.get("content-disposition", "")

    def test_filters_are_accepted(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        db = _override_db([_audit_log(action="delete")])

        response = client.get(
            "/api/v1/admin/compliance/report",
            params={
                "start": "2026-01-01T00:00:00",
                "end": "2026-12-31T23:59:59Z",
                "actor": "admin-1",
                "action": "delete",
                "limit": 5,
            },
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )

        assert response.status_code == 200
        db.execute.assert_awaited_once()
        assert response.json()["filters"]["actor"] == "admin-1"

    def test_invalid_format_is_422(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        _override_db([])

        response = client.get(
            "/api/v1/admin/compliance/report",
            params={"format": "xml"},
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )
        assert response.status_code == 422

    def test_invalid_timestamp_is_422(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        _override_db([])

        response = client.get(
            "/api/v1/admin/compliance/report",
            params={"start": "not-a-date"},
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )
        assert response.status_code == 422

    def test_non_admin_is_403(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        _override_db([])

        response = client.get(
            "/api/v1/admin/compliance/report",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "agent"},
        )
        assert response.status_code == 403

    def test_admin_guard_allows_admin(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        _override_db([])

        response = client.get(
            "/api/v1/admin/compliance/report",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )
        assert response.status_code == 200
