"""
ODW.ai Desk — Unit Tests for RBAC (F-RBAC-Desk, DA1-DA3)

Covers role resolution (JWT claim > X-Desk-Role header > configured default),
the ``require_role`` dependency (open when no key, 401 on bad key, 403 when the
role is insufficient, pass when sufficient), and router wiring (agent on an
admin route -> 403, admin -> 200, open when no key configured).
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from desk.config import get_settings
from desk.main import app
from desk.security.rbac import require_role, resolve_role


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def _make_jwt(role: str) -> str:
    settings = get_settings()
    return jwt.encode({"role": role}, settings.secret_key, algorithm="HS256")


class TestResolveRole:
    """Role resolution priority: JWT claim > header > configured default."""

    def test_jwt_claim_wins(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        settings = get_settings()

        role = resolve_role(
            settings, authorization=f"Bearer {_make_jwt('agent')}", desk_role="admin"
        )
        assert role == "agent"

    def test_header_used_without_jwt(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        settings = get_settings()

        assert resolve_role(settings, authorization=None, desk_role="Agent") == "agent"

    def test_default_when_nothing_supplied(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        settings = get_settings()

        # Default role is least-privileged agent (default-deny for admin routes).
        assert resolve_role(settings, authorization=None, desk_role=None) == "agent"

    def test_invalid_header_does_not_escalate(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        settings = get_settings()

        # An unrecognised role header must fall back to the least-privileged
        # default, never silently escalate to admin.
        assert resolve_role(settings, authorization=None, desk_role="superuser") == "agent"

    def test_admin_still_available_explicitly(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()
        settings = get_settings()

        assert resolve_role(settings, authorization=None, desk_role="admin") == "admin"


class TestRequireRoleDependency:
    """Direct unit tests for the require_role dependency logic."""

    async def test_open_when_no_key_configured(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "")
        get_settings.cache_clear()

        dependency = require_role("admin")
        assert await dependency(x_api_key=None, authorization=None, desk_role=None) is None

    async def test_bad_key_is_401(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        dependency = require_role("agent")
        with pytest.raises(HTTPException) as exc:
            await dependency(x_api_key="wrong", authorization=None, desk_role="admin")
        assert exc.value.status_code == 401

    async def test_agent_on_admin_is_403(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        dependency = require_role("admin")
        with pytest.raises(HTTPException) as exc:
            await dependency(x_api_key="sekret", authorization=None, desk_role="agent")
        assert exc.value.status_code == 403

    async def test_admin_satisfies_admin(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        dependency = require_role("admin")
        role = await dependency(x_api_key="sekret", authorization=None, desk_role="admin")
        assert role == "admin"

    async def test_admin_satisfies_agent_requirement(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        dependency = require_role("agent")
        role = await dependency(x_api_key="sekret", authorization=None, desk_role="admin")
        assert role == "admin"

    async def test_jwt_role_is_respected(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        dependency = require_role("admin")
        with pytest.raises(HTTPException) as exc:
            await dependency(
                x_api_key=None, authorization=f"Bearer {_make_jwt('agent')}", desk_role=None
            )
        assert exc.value.status_code == 403


class TestRbacWiring:
    """Prove the role guards are applied to the admin/agent routers."""

    def test_agent_on_admin_route_is_403(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        response = client.get(
            "/api/v1/admin/compliance/reports",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "agent"},
        )
        assert response.status_code == 403

    def test_unknown_role_header_on_admin_route_is_403(self, client, monkeypatch):
        """Regression: unknown/absent role headers must not get admin by default."""
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        response = client.get(
            "/api/v1/admin/compliance/reports",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "superuser"},
        )
        assert response.status_code == 403

    def test_no_role_header_on_admin_route_is_403(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        response = client.get("/api/v1/admin/compliance/reports", headers={"X-API-Key": "sekret"})
        assert response.status_code == 403

    def test_admin_on_admin_route_is_200(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        response = client.get(
            "/api/v1/admin/compliance/reports",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "admin"},
        )
        assert response.status_code == 200

    def test_admin_route_open_when_key_unset(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "")
        get_settings.cache_clear()

        response = client.get("/api/v1/admin/compliance/reports")
        assert response.status_code == 200

    def test_agent_route_not_forbidden_for_agent(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        # agent satisfies the agent+ guard, so it must NOT be a 403 (the request
        # may still fail later with no DB in unit tests, but not at the guard).
        response = client.get(
            "/api/v1/agents/conversations",
            headers={"X-API-Key": "sekret", "X-Desk-Role": "agent"},
        )
        assert response.status_code != 403
