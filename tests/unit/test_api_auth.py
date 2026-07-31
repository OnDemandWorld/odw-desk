"""
ODW.ai Desk — Unit Tests for the Optional API Key Guard

The guard (``desk.security.api_auth.require_api_key``) protects the admin and
agent inbox routers when ``DESK_API_KEY`` is set, and is a no-op when unset
(backward compatible). Health and webhook routes are never guarded.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from desk.config import get_settings
from desk.main import app
from desk.security.api_auth import require_api_key


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


class TestRequireApiKeyDependency:
    """Direct unit tests for the dependency logic."""

    async def test_unset_key_is_open(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "")
        get_settings.cache_clear()

        # No exception -> open.
        assert await require_api_key(x_api_key=None, authorization=None) is None

    async def test_set_key_blocks_without_key(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        with pytest.raises(HTTPException) as exc:
            await require_api_key(x_api_key=None, authorization=None)
        assert exc.value.status_code == 401

    async def test_set_key_allows_matching_x_api_key(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        assert await require_api_key(x_api_key="sekret", authorization=None) is None

    async def test_set_key_allows_matching_bearer_token(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        assert await require_api_key(x_api_key=None, authorization="Bearer sekret") is None

    async def test_set_key_rejects_wrong_key(self, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        with pytest.raises(HTTPException) as exc:
            await require_api_key(x_api_key="nope", authorization=None)
        assert exc.value.status_code == 401


class TestApiKeyGuardWiring:
    """Prove the guard is actually applied to the admin/agent routers."""

    def test_agents_route_blocked_without_key(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        response = client.get("/api/v1/agents/conversations")
        assert response.status_code == 401

    def test_admin_route_blocked_without_key(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        response = client.get("/api/v1/admin/setup/status")
        assert response.status_code == 401

    def test_agents_route_open_when_key_unset(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "")
        get_settings.cache_clear()

        # Guard is a no-op -> request passes the guard (not a 401). It may still
        # fail later (e.g. no DB in unit tests), but it must NOT be blocked.
        response = client.get("/api/v1/agents/conversations")
        assert response.status_code != 401

    def test_webhooks_stay_open_when_key_set(self, client, monkeypatch):
        monkeypatch.setenv("DESK_API_KEY", "sekret")
        get_settings.cache_clear()

        # Webhook GET verification handshake is not guarded.
        response = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "dev_verify_token",
                "hub.challenge": "challenge-123",
            },
        )
        assert response.status_code == 200
