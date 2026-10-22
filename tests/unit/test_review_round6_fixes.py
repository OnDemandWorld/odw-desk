"""
ODW.ai Desk — Unit Tests for the V1.7 deep-review round fixes.

Covers:
- D-1: policy engine actions actually wired in the AI pipeline
  (redirect / escalate / append_disclaimer — previously silently dropped).
- D-2: POST /api/v1/admin/agents + /personas + GET /agents (takeover bootstrap).
- D-3/D-4: runtime settings persistence + AIEngine runtime-config refresh.
- D-5: first-response SLA honours settings.sla_first_response_minutes.
- D-12: JWT bearer reaches admin routes without the shared API key.

Mock-based style matching the existing unit suite (no real database).
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from desk.config import get_settings
from desk.dependencies import get_db
from desk.main import app


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    get_settings.cache_clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers(role: str = "admin") -> dict[str, str]:
    """A signed admin JWT (test secret) — the JWT-only auth path."""
    import time

    from jose import jwt

    secret = get_settings().secret_key
    now = int(time.time())
    token = jwt.encode(
        {"sub": "user-1", "role": role, "iat": now, "exp": now + 600},
        secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# ─── D-1: policy actions in the AI pipeline ─────────────────────────────────


class TestPolicyRedirectWiring:
    def _engine_with_policy(self, decision: str, redirect_response: str | None = None):
        from desk.ai.engine import AIEngine, AIResult

        engine = AIEngine.__new__(AIEngine)
        policy_result = {
            "policy_decision": decision,
            "triggers": ["keyword:competitor"],
            "redirect_response": redirect_response,
        }
        engine_policy = MagicMock()
        engine_policy.run_pre_generation_hooks = AsyncMock(return_value=policy_result)
        # Post-hooks: no violations, no disclaimers.
        engine_policy.run_post_generation_hooks = AsyncMock(
            return_value={"is_valid": True, "violations": [], "append_texts": [], "action": "allow"}
        )
        pii = SimpleNamespace(
            pii_detected=False,
            pii_types=[],
            redacted_text="msg",
            routing_directive=SimpleNamespace(value="NO_RESTRICTION"),
        )
        engine.pii_shield = SimpleNamespace(analyze=AsyncMock(return_value=pii))
        engine.model_router = SimpleNamespace(
            route=AsyncMock(
                return_value=SimpleNamespace(
                    target=SimpleNamespace(value="LOCAL"),
                    model_name="qwen",
                )
            )
        )
        engine.vault_client = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
        engine._escalate_conversation = AsyncMock()
        return engine, engine_policy

    @staticmethod
    def _patched_session():
        sess = MagicMock()
        sess.__aenter__ = AsyncMock(return_value=MagicMock())
        sess.__aexit__ = AsyncMock(return_value=False)
        return sess

    @pytest.mark.asyncio
    async def test_redirect_decision_returns_canned_reply(self):
        from desk.ai.engine import AIEngine

        engine, policy = self._engine_with_policy("redirect", "We recommend ODW!")
        with patch("desk.ai.engine.PolicyEngine", return_value=policy), patch(
            "desk.ai.engine.AsyncSessionLocal", return_value=self._patched_session()
        ):
            result = await engine.process_detailed(
                str(uuid4()), "what about competitorX", "webchat", "v1"
            )
        assert result.blocked is True
        assert result.text == "We recommend ODW!"

    @pytest.mark.asyncio
    async def test_escalate_decision_escalates_and_notifies(self):
        from desk.ai.engine import AIEngine

        engine, policy = self._engine_with_policy("escalate")
        with patch("desk.ai.engine.PolicyEngine", return_value=policy), patch(
            "desk.ai.engine.AsyncSessionLocal", return_value=self._patched_session()
        ):
            result = await engine.process_detailed(str(uuid4()), "help", "webchat", "v1")
        assert result.escalated is True
        engine._escalate_conversation.assert_awaited_once()


class TestPostPolicyDisclaimer:
    @pytest.mark.asyncio
    async def test_append_disclaimer_attaches_text(self):
        from desk.ai.engine import AIEngine

        engine = AIEngine.__new__(AIEngine)
        policy = MagicMock()
        policy.run_pre_generation_hooks = AsyncMock(
            return_value={"policy_decision": "allow", "triggers": [], "redirect_response": None}
        )
        policy.run_post_generation_hooks = AsyncMock(
            return_value={
                "is_valid": True,
                "violations": [],
                "append_texts": ["Consult a professional."],
                "action": "allow",
            }
        )
        pii = SimpleNamespace(
            pii_detected=False,
            pii_types=[],
            redacted_text="q",
            routing_directive=SimpleNamespace(value="NO_RESTRICTION"),
        )
        engine.pii_shield = SimpleNamespace(analyze=AsyncMock(return_value=pii))
        engine.model_router = SimpleNamespace(
            route=AsyncMock(
                return_value=SimpleNamespace(target=SimpleNamespace(value="LOCAL"), model_name="qwen")
            )
        )
        engine.vault_client = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
        engine.local_provider = SimpleNamespace(
            generate=AsyncMock(
                return_value=SimpleNamespace(
                    text="Answer body", provider="ollama", model="qwen", tokens_used=10, metadata={}
                )
            )
        )
        engine.confidence_scorer = SimpleNamespace(
            score=AsyncMock(
                return_value=SimpleNamespace(
                    score=0.95, should_escalate=False, reasoning="ok", factors={}
                )
            )
        )
        # Persona/vault prompt path
        sess = MagicMock()
        sess.__aenter__ = AsyncMock(return_value=MagicMock())
        sess.__aexit__ = AsyncMock(return_value=False)
        with patch("desk.ai.engine.PolicyEngine", return_value=policy), patch(
            "desk.ai.engine.AsyncSessionLocal", return_value=sess
        ), patch("desk.ai.engine.get_prompt_builder_with_persona") as gp:
            gp.return_value = AsyncMock()
            gp.return_value.build_prompt_with_persona = AsyncMock(return_value=("sys", "prompt"))
            result = await engine.process_detailed(str(uuid4()), "q", "webchat", "v1")
        assert "Answer body" in result.text
        assert "Consult a professional." in result.text


# ─── D-2: agent / persona creation endpoints ────────────────────────────────


class TestAgentPersonaCreation:
    def test_create_agent_persists_and_lists(self, client):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(
            side_effect=lambda obj: setattr(
                obj,
                "id",
                getattr(obj, "id", None) or uuid4(),
            )
        )
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[]))
                )
            )
        )
        app.dependency_overrides[get_db] = lambda: db
        res = client.post(
            "/api/v1/admin/agents",
            json={"display_name": "Alice", "email": "alice@example.com", "role": "agent"},
            headers=_auth_headers("admin"),
        )
        assert res.status_code == 201, res.text
        assert res.json()["email"] == "alice@example.com"

    def test_create_persona_validates_tone(self, client):
        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        res = client.post(
            "/api/v1/admin/personas",
            json={"name": "Warm", "tone": ""},
            headers=_auth_headers("admin"),
        )
        assert res.status_code == 422


# ─── D-3: setup endpoints persist ───────────────────────────────────────────


class TestSetupPersistence:
    def test_setup_vault_persists_and_resets_client(self, client):
        from desk.admin import runtime_settings

        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        db.add = MagicMock()
        db.commit = AsyncMock()
        app.dependency_overrides[get_db] = lambda: db
        with patch("desk.ai.vault_client.reset_vault_client") as reset:
            res = client.post(
                "/api/v1/admin/setup/vault",
                params={"vault_url": "http://vault:8765", "vault_api_key": "", "collection_id": "c1"},
                headers=_auth_headers("admin"),
            )
        assert res.status_code == 200
        assert res.json()["success"] is True
        reset.assert_called_once()
        assert runtime_settings.get_override("vault") == {
            "vault_url": "http://vault:8765",
            "vault_api_key": "",
            "vault_collection_id": "c1",
        }

    def test_setup_ai_model_rejects_anthropic(self, client):
        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        res = client.post(
            "/api/v1/admin/setup/ai-model",
            params={"provider": "anthropic", "model_name": "claude-3.5-sonnet"},
            headers=_auth_headers("admin"),
        )
        assert res.status_code == 400
        assert "not implemented" in res.json()["detail"]


# ─── D-5: SLA from config ───────────────────────────────────────────────────


class TestSlaFromConfig:
    @pytest.mark.asyncio
    async def test_first_response_sla_uses_setting(self):
        from desk.conversations.manager import ConversationManager
        from desk.models.conversation import Conversation
        from desk.conversations.state_machine import ConversationStatus

        conversation = Conversation(
            customer_id=uuid4(),
            channel="webchat",
            channel_conversation_id="w-1",
            status=ConversationStatus.NEW,
        )
        db = MagicMock()
        db.flush = AsyncMock()
        manager = ConversationManager(db)
        with patch.object(
            ConversationManager,
            "_ensure_first_response_sla",
            ConversationManager._ensure_first_response_sla,
        ):
            await manager._ensure_first_response_sla(conversation)
        assert conversation.sla_first_response_due is not None
        minutes = (
            datetime.now(tz=UTC) - conversation.sla_first_response_due.replace(tzinfo=UTC)
            if conversation.sla_first_response_due.tzinfo is None
            else datetime.now(tz=UTC) - conversation.sla_first_response_due
        ).total_seconds() / 60
        # Configured value (default 10) — assert it is a positive, plausible SLA
        # window rather than a hardcoded literal so config changes don't break.
        assert 0 < -minutes or minutes < 0  # due is in the future
        assert abs(minutes + get_settings().sla_first_response_minutes) < 1


# ─── D-12: JWT-only bearer reaches admin routes ─────────────────────────────


class TestJwtOnlyAuthPath:
    def test_admin_route_accepts_jwt_bearer_without_api_key(self, client):
        settings = get_settings()
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        )
        app.dependency_overrides[get_db] = lambda: db
        with patch(
            "desk.security.rbac.get_settings",
            return_value=SimpleNamespace(
                desk_api_key="a-different-shared-key",
                secret_key=settings.secret_key,
                desk_default_role="agent",
            ),
        ):
            res = client.get(
                "/api/v1/admin/setup/status", headers=_auth_headers("admin")
            )
        assert res.status_code != 401
        assert res.status_code != 403
