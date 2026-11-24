"""
Regression tests for full-audit round 1, batch 2 (.ocr-reports/full-audit.json).

Covers:
- #1  admin/agent guards fail closed without DESK_API_KEY outside development
- #15 X-Desk-Role header no longer trusted in staging
- #2  setup endpoints take secrets in the JSON body, not query parameters
- #5  conversation creation race / multi-participant thread reuses existing row
- #7  MessageRouter commits before publishing the routed event
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt
from sqlalchemy.exc import IntegrityError

from desk.config import Settings
from desk.security.rbac import require_role, resolve_role


def _settings(environment: str, desk_api_key: str = "") -> Settings:
    return Settings(
        environment=environment,
        secret_key="a" * 64,
        desk_api_key=desk_api_key,
    )


def _jwt(role: str, settings: Settings) -> str:
    return jose_jwt.encode({"role": role}, settings.secret_key, algorithm="HS256")


class TestFailClosedAuth:
    """#1: no DESK_API_KEY must not leave admin/agent routes open in prod/staging."""

    async def test_production_no_key_no_jwt_rejected(self) -> None:
        settings = _settings("production")
        dep = require_role("admin")
        with patch("desk.security.rbac.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc:
                await dep(x_api_key=None, authorization=None, desk_role=None)
        assert exc.value.status_code == 401

    async def test_staging_no_key_no_jwt_rejected(self) -> None:
        settings = _settings("staging")
        dep = require_role("agent")
        with patch("desk.security.rbac.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc:
                await dep(x_api_key=None, authorization=None, desk_role=None)
        assert exc.value.status_code == 401

    async def test_production_valid_jwt_admin_accepted(self) -> None:
        settings = _settings("production")
        dep = require_role("admin")
        token = _jwt("admin", settings)
        with patch("desk.security.rbac.get_settings", return_value=settings):
            role = await dep(x_api_key=None, authorization=f"Bearer {token}", desk_role=None)
        assert role == "admin"

    async def test_production_agent_jwt_insufficient_for_admin(self) -> None:
        settings = _settings("production")
        dep = require_role("admin")
        token = _jwt("agent", settings)
        with patch("desk.security.rbac.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc:
                await dep(x_api_key=None, authorization=f"Bearer {token}", desk_role=None)
        assert exc.value.status_code == 403

    async def test_development_no_key_stays_open(self) -> None:
        settings = _settings("development")
        dep = require_role("admin")
        with patch("desk.security.rbac.get_settings", return_value=settings):
            assert await dep(x_api_key=None, authorization=None, desk_role=None) is None


class TestRoleHeaderTrust:
    """#15: self-asserted X-Desk-Role must not grant admin in staging."""

    def test_staging_header_not_trusted(self) -> None:
        settings = _settings("staging", desk_api_key="k")
        assert resolve_role(settings, desk_role="admin") == "agent"

    def test_development_header_trusted(self) -> None:
        settings = _settings("development", desk_api_key="k")
        assert resolve_role(settings, desk_role="admin") == "admin"

    def test_explicit_override_still_honored(self) -> None:
        settings = Settings(
            environment="staging",
            secret_key="a" * 64,
            desk_api_key="k",
            desk_role_header_trusted=True,
        )
        assert resolve_role(settings, desk_role="admin") == "admin"


class TestSetupSecretsInBody:
    """#2: setup endpoints must reject query-string secrets (422) and accept bodies."""

    def _client(self) -> TestClient:
        from desk.admin.api import router as admin_router
        from desk.dependencies import get_db

        app = FastAPI()
        app.include_router(admin_router)
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        db.add = MagicMock()
        db.commit = AsyncMock()
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_vault_query_params_rejected(self) -> None:
        client = self._client()
        res = client.post(
            "/api/v1/admin/setup/vault",
            params={"vault_url": "http://v", "vault_api_key": "secret", "collection_id": "c"},
        )
        assert res.status_code == 422

    def test_vault_body_accepted(self) -> None:
        client = self._client()
        with patch("desk.ai.vault_client.reset_vault_client"):
            res = client.post(
                "/api/v1/admin/setup/vault",
                json={"vault_url": "http://v", "vault_api_key": "secret", "collection_id": "c"},
            )
        assert res.status_code == 200
        assert res.json()["success"] is True

    def test_whatsapp_query_params_rejected(self) -> None:
        client = self._client()
        res = client.post(
            "/api/v1/admin/setup/whatsapp",
            params={
                "access_token": "secret",
                "phone_number_id": "1",
                "business_account_id": "2",
                "webhook_verify_token": "secret2",
            },
        )
        assert res.status_code == 422

    def test_ai_model_query_params_rejected(self) -> None:
        client = self._client()
        res = client.post(
            "/api/v1/admin/setup/ai-model",
            params={"provider": "openai", "model_name": "gpt-4o-mini", "api_key": "secret"},
        )
        assert res.status_code == 422


class TestConversationThreadCollision:
    """#5: losing a creation race must re-read the winner, not 500."""

    async def test_integrity_error_rereads_existing_thread(self) -> None:
        from desk.conversations.manager import ConversationManager

        manager = ConversationManager(MagicMock())
        existing = MagicMock()
        existing.id = uuid4()

        miss = MagicMock()
        miss.scalar_one_or_none.return_value = None
        hit = MagicMock()
        hit.scalar_one_or_none.return_value = existing
        manager.db.execute = AsyncMock(side_effect=[miss, hit])
        manager.db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("duplicate key"))
        )
        manager.db.rollback = AsyncMock()
        manager.db.add = MagicMock()

        customer = MagicMock()
        customer.id = uuid4()
        result = await manager.get_or_create_conversation(
            customer=customer, channel="email", channel_conversation_id="email-msg:root"
        )
        assert result is existing
        manager.db.rollback.assert_awaited_once()

    async def test_integrity_error_without_winner_reraises(self) -> None:
        from desk.conversations.manager import ConversationManager

        manager = ConversationManager(MagicMock())
        miss = MagicMock()
        miss.scalar_one_or_none.return_value = None
        manager.db.execute = AsyncMock(side_effect=[miss, miss])
        manager.db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("duplicate key"))
        )
        manager.db.rollback = AsyncMock()
        manager.db.add = MagicMock()

        customer = MagicMock()
        customer.id = uuid4()
        with pytest.raises(IntegrityError):
            await manager.get_or_create_conversation(
                customer=customer, channel="email", channel_conversation_id="email-msg:root"
            )


class TestCommitBeforePublish:
    """#7: the routed event must only be published after a successful commit."""

    async def test_commit_precedes_publish(self) -> None:
        from desk.router.message_router import MessageRouter
        from desk.schemas.channels import InboundMessage

        order: list[str] = []
        router = MessageRouter(MagicMock(), MagicMock())
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        router.db.execute = AsyncMock(return_value=dup_result)
        router.db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
        router.event_bus.publish = AsyncMock(side_effect=lambda *a, **k: order.append("publish"))
        customer = MagicMock()
        customer.id = uuid4()
        conversation = MagicMock()
        conversation.id = uuid4()
        router.customer_resolver.resolve_or_create = AsyncMock(return_value=customer)
        router.conversation_manager.get_or_create_conversation = AsyncMock(
            return_value=conversation
        )
        router.conversation_manager.add_message = AsyncMock(return_value=MagicMock())

        inbound = InboundMessage(
            message_id="m-commit-order",
            conversation_id="thread-order",
            channel="whatsapp",
            sender_identifier="+123",
            sender_type="customer",
            content="hello",
        )
        result = await router.route(inbound)
        assert result["status"] == "routed"
        assert order == ["commit", "publish"]

    async def test_commit_failure_does_not_publish(self) -> None:
        from desk.router.message_router import MessageRouter
        from desk.schemas.channels import InboundMessage

        router = MessageRouter(MagicMock(), MagicMock())
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        router.db.execute = AsyncMock(return_value=dup_result)
        router.db.commit = AsyncMock(side_effect=RuntimeError("db down"))
        router.event_bus.publish = AsyncMock()
        customer = MagicMock()
        customer.id = uuid4()
        conversation = MagicMock()
        conversation.id = uuid4()
        router.customer_resolver.resolve_or_create = AsyncMock(return_value=customer)
        router.conversation_manager.get_or_create_conversation = AsyncMock(
            return_value=conversation
        )
        router.conversation_manager.add_message = AsyncMock(return_value=MagicMock())

        inbound = InboundMessage(
            message_id="m-commit-fail",
            conversation_id="thread-fail",
            channel="whatsapp",
            sender_identifier="+123",
            sender_type="customer",
            content="hello",
        )
        with pytest.raises(RuntimeError):
            await router.route(inbound)
        router.event_bus.publish.assert_not_awaited()
