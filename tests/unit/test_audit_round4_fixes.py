"""
Regression tests for full-audit round 1, batch 4 (.ocr-reports/full-audit.json).

Covers:
- #28 AI feedback persisted via new-dict JSONB assignment
- #29 status-change reason persisted on conversations with existing metadata
- #30 activating an unknown persona returns 404 and deactivates nothing
- #35 runtime overrides loaded at startup (load_all wired into lifespan)
- #36 WhatsApp adapter consumes the persisted setup override
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from desk.dependencies import get_db
from desk.main import app


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestFeedbackJsonb:
    """#28: feedback must land in a NEW dict so SQLAlchemy emits the UPDATE."""

    def test_feedback_preserves_existing_metadata(self) -> None:
        from desk.models.message import Message

        original = {"confidence": 0.9}
        message = Message(content="reply", sender_type="ai", metadata_=original)
        result = MagicMock()
        result.scalar_one_or_none.return_value = message
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        app.dependency_overrides[get_db] = lambda: db

        client = TestClient(app)
        res = client.post(f"/api/v1/agents/messages/{uuid4()}/feedback?feedback=thumbs_down")
        assert res.status_code == 200
        assert message.metadata_ == {"confidence": 0.9, "agent_feedback": "thumbs_down"}
        # New dict assigned — same-object reassignment would emit no UPDATE.
        assert message.metadata_ is not original
        assert original == {"confidence": 0.9}  # original untouched


class TestStatusReasonJsonb:
    """#29: reason must persist even when metadata already has content."""

    async def test_reason_merged_into_existing_metadata(self, monkeypatch) -> None:
        from desk.conversations.manager import ConversationManager
        from desk.conversations.state_machine import ConversationStatus

        manager = ConversationManager(MagicMock())
        manager.db.flush = AsyncMock()
        monkeypatch.setattr(manager, "_mark_resolution", AsyncMock())

        conv = MagicMock()
        conv.status = ConversationStatus.ACTIVE
        existing = {"csat": {"rating": 5}}
        conv.metadata_ = existing

        await manager.update_status(conv, ConversationStatus.RESOLVED, reason="resolved by agent")
        assert conv.metadata_ == {
            "csat": {"rating": 5},
            "last_status_change_reason": "resolved by agent",
        }
        assert conv.metadata_ is not existing


class TestPersonaActivation:
    """#30: unknown persona id must not deactivate all personas."""

    async def test_unknown_id_touches_nothing(self, monkeypatch) -> None:
        from desk.persona.service import PersonaService

        service = PersonaService(MagicMock())
        monkeypatch.setattr(service, "get_persona_by_id", AsyncMock(return_value=None))
        service.db.execute = AsyncMock()
        service.db.commit = AsyncMock()

        assert await service.activate_persona(uuid4()) is False
        service.db.execute.assert_not_awaited()
        service.db.commit.assert_not_awaited()

    async def test_known_id_deactivates_others_and_activates_target(self, monkeypatch) -> None:
        from desk.persona.service import PersonaService

        service = PersonaService(MagicMock())
        target = MagicMock()
        target.is_active = False
        other = MagicMock()
        other.is_active = True
        monkeypatch.setattr(service, "get_persona_by_id", AsyncMock(return_value=target))
        result = MagicMock()
        result.scalars.return_value.all.return_value = [other, target]
        service.db.execute = AsyncMock(return_value=result)
        service.db.commit = AsyncMock()

        assert await service.activate_persona(uuid4()) is True
        assert other.is_active is False
        assert target.is_active is True
        service.db.commit.assert_awaited_once()

    def test_endpoint_returns_404_for_unknown_persona(self) -> None:
        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        service = MagicMock()
        service.activate_persona = AsyncMock(return_value=False)
        with patch("desk.admin.persona_policy_api.PersonaService", return_value=service):
            client = TestClient(app)
            res = client.post(f"/api/v1/admin/personas/{uuid4()}/activate")
        assert res.status_code == 404


class TestStartupLoadsOverrides:
    """#35: lifespan must call runtime_settings.load_all."""

    def test_lifespan_calls_load_all(self) -> None:
        import desk.main as main_mod

        redis_manager = MagicMock()
        redis_manager.connect = AsyncMock()
        redis_manager.disconnect = AsyncMock()
        event_bus = MagicMock()
        event_bus.connect = AsyncMock()
        event_bus.disconnect = AsyncMock()
        channel_manager = MagicMock()
        channel_manager.start_all = AsyncMock()
        channel_manager.stop_all = AsyncMock()
        processor = MagicMock()
        processor.run = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_cm.__aexit__ = AsyncMock(return_value=False)
        license_manager = MagicMock()
        license_manager.initialize = AsyncMock()
        engine = MagicMock()
        engine.dispose = AsyncMock()
        load_all = AsyncMock(return_value={})

        with (
            patch.object(main_mod, "get_redis_manager", return_value=redis_manager),
            patch.object(main_mod, "RedisStreamsEventBus", return_value=event_bus),
            patch.object(main_mod, "ChannelAdapterManager", return_value=channel_manager),
            patch.object(main_mod, "get_whatsapp_adapter", return_value=None),
            patch.object(main_mod, "WebChatAdapter", return_value=MagicMock()),
            patch.object(main_mod, "EmailChannelAdapter", return_value=MagicMock()),
            patch.object(main_mod, "MessageProcessor", return_value=processor),
            patch.object(main_mod, "AIEngine", return_value=MagicMock()),
            patch.object(main_mod, "AsyncSessionLocal", return_value=session_cm),
            patch.object(main_mod, "scan_due_conversations", new=AsyncMock(return_value={})),
            patch.object(main_mod, "get_engine", return_value=engine),
            patch("desk.license.manager.LicenseManager", return_value=license_manager),
            patch("desk.admin.runtime_settings.load_all", new=load_all),
        ):
            with TestClient(app):
                pass

        load_all.assert_awaited_once()


class TestWhatsAppOverrideConsumed:
    """#36: the persisted setup override must reach the adapter and webhook."""

    async def test_send_uses_override_credentials(self) -> None:
        from desk.channels.base import AdapterConfig
        from desk.channels.whatsapp_business import WhatsAppBusinessAdapter
        from desk.schemas.channels import OutboundMessage

        adapter = WhatsAppBusinessAdapter(
            AdapterConfig(
                adapter_id="wa-1",
                adapter_name="WA",
                channel_type="whatsapp_business",
                enabled=True,
            )
        )
        override = {
            "access_token": "override-token",
            "phone_number_id": "override-phone",
        }
        msg = OutboundMessage(
            conversation_id="c", channel="whatsapp", recipient_identifier="+1", content="hi"
        )
        response = MagicMock()
        response.json.return_value = {"messages": [{"id": "wamid.1"}]}
        client = MagicMock()
        client.post = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("desk.admin.runtime_settings.get_override", return_value=override),
            patch("desk.channels.whatsapp_business.httpx.AsyncClient", return_value=client),
        ):
            result = await adapter.send(msg)

        assert result["success"] is True
        url = client.post.await_args.args[0]
        headers = client.post.await_args.kwargs["headers"]
        assert "override-phone" in url
        assert headers["Authorization"] == "Bearer override-token"

    def test_effective_config_prefers_override(self) -> None:
        from desk.channels.whatsapp_business import _effective_whatsapp_config

        override = {"access_token": "ov-token", "webhook_verify_token": "ov-verify"}
        with patch("desk.admin.runtime_settings.get_override", return_value=override):
            cfg = _effective_whatsapp_config()
        assert cfg["access_token"] == "ov-token"
        assert cfg["webhook_verify_token"] == "ov-verify"

    def test_effective_config_falls_back_to_env(self) -> None:
        from desk.channels.whatsapp_business import _effective_whatsapp_config
        from desk.config import get_settings

        with patch("desk.admin.runtime_settings.get_override", return_value=None):
            cfg = _effective_whatsapp_config()
        assert cfg["access_token"] == get_settings().whatsapp_access_token
