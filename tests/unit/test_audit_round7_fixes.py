"""
Regression tests for full-audit round 1, batch 7 (.ocr-reports/full-audit.json).

Covers authorization & attribution hardening:
- #16 acting agent bound to the JWT principal (no client-chosen impersonation)
- #17 /status requires ownership for assigned conversations + row lock
- #18 compliance audit actor derived from the JWT principal
- #19 read receipts scoped to the visitor's own conversation
- #26 webchat error frames no longer leak internal exception text
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from desk.config import get_settings


def _jwt(sub: str) -> str:
    now = int(time.time())
    return jose_jwt.encode(
        {"sub": sub, "role": "agent", "iat": now, "exp": now + 600},
        get_settings().secret_key,
        algorithm="HS256",
    )


def _request_with_bearer(token: str | None) -> MagicMock:
    request = MagicMock()
    headers = {"authorization": f"Bearer {token}"} if token else {}
    request.headers.get = lambda key, default="": headers.get(key, default)
    return request


class TestActingAgentBinding:
    """#16: JWT sub -> Agent row overrides the client-supplied agent_id."""

    async def test_jwt_principal_overrides_supplied_agent(self) -> None:
        from desk.agents.inbox_api import _acting_agent_id

        real_agent_id = uuid4()
        user_id = uuid4()
        agent = SimpleNamespace(id=real_agent_id)
        result = MagicMock()
        result.scalars.return_value.first.return_value = agent
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        supplied = uuid4()  # someone else's agent id
        acting = await _acting_agent_id(_request_with_bearer(_jwt(str(user_id))), supplied, db)
        assert acting == real_agent_id

    async def test_no_jwt_keeps_supplied(self) -> None:
        from desk.agents.inbox_api import _acting_agent_id

        supplied = uuid4()
        db = MagicMock()
        db.execute = AsyncMock()
        acting = await _acting_agent_id(_request_with_bearer(None), supplied, db)
        assert acting == supplied
        db.execute.assert_not_awaited()

    async def test_jwt_without_matching_agent_keeps_supplied(self) -> None:
        from desk.agents.inbox_api import _acting_agent_id

        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        supplied = uuid4()
        acting = await _acting_agent_id(
            _request_with_bearer(_jwt(str(uuid4()))), supplied, db
        )
        assert acting == supplied


class TestStatusOwnership:
    """#17: assigned conversations cannot be transitioned by another agent."""

    async def test_assigned_conversation_rejects_other_agent(self) -> None:
        from desk.agents.inbox_api import ConversationStatusUpdate, update_conversation_status

        owner = uuid4()
        conversation = MagicMock()
        conversation.assigned_agent_id = owner
        result = MagicMock()
        result.scalar_one_or_none.return_value = conversation
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        payload = ConversationStatusUpdate(status="resolved")
        with pytest.raises(HTTPException) as exc:
            await update_conversation_status(
                conversation_id=uuid4(),
                payload=payload,
                request=MagicMock(),
                agent_id=uuid4(),  # not the owner
                role="agent",
                db=db,
            )
        assert exc.value.status_code == 403
        # Row lock requested (with_for_update compiles into the query).
        query = db.execute.await_args.args[0]
        assert query._for_update_arg is not None

    async def test_owner_may_transition(self) -> None:
        from desk.agents.inbox_api import ConversationStatusUpdate, update_conversation_status

        owner = uuid4()
        conversation = MagicMock()
        conversation.id = uuid4()
        conversation.assigned_agent_id = owner
        conversation.status = "resolved"
        result = MagicMock()
        result.scalar_one_or_none.return_value = conversation
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        manager = MagicMock()
        manager.update_status = AsyncMock()
        with (
            patch("desk.agents.inbox_api.ConversationManager", return_value=manager),
            patch("desk.agents.inbox_api.broadcast_conversation_update", new=AsyncMock()),
        ):
            out = await update_conversation_status(
                conversation_id=conversation.id,
                payload=ConversationStatusUpdate(status="resolved"),
                request=MagicMock(),
                agent_id=owner,
                role="agent",
                db=db,
            )
        assert out["success"] is True

    async def test_admin_bypasses_ownership(self) -> None:
        from desk.agents.inbox_api import ConversationStatusUpdate, update_conversation_status

        conversation = MagicMock()
        conversation.id = uuid4()
        conversation.assigned_agent_id = uuid4()
        conversation.status = "closed"
        result = MagicMock()
        result.scalar_one_or_none.return_value = conversation
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        manager = MagicMock()
        manager.update_status = AsyncMock()
        with (
            patch("desk.agents.inbox_api.ConversationManager", return_value=manager),
            patch("desk.agents.inbox_api.broadcast_conversation_update", new=AsyncMock()),
        ):
            out = await update_conversation_status(
                conversation_id=conversation.id,
                payload=ConversationStatusUpdate(status="closed"),
                request=MagicMock(),
                agent_id=None,
                role="admin",
                db=db,
            )
        assert out["success"] is True


class TestAuditActor:
    """#18: JWT sub overrides the caller-claimed actor_id."""

    def test_jwt_sub_overrides_claimed(self) -> None:
        from desk.admin.api import _audit_actor

        actor = _audit_actor(_request_with_bearer(_jwt("auditor-1")), "victim-uuid")
        assert actor == "auditor-1"

    def test_no_jwt_falls_back_to_claimed(self) -> None:
        from desk.admin.api import _audit_actor

        assert _audit_actor(_request_with_bearer(None), "system") == "system"


class TestReadReceiptScoping:
    """#19: a visitor cannot mark another customer's message read."""

    async def test_foreign_message_not_marked(self) -> None:
        from desk.channels.webchat import mark_message_read
        from desk.models.message import Message

        message = Message(content="hi", sender_type="customer", channel_message_id="m1")
        msg_result = MagicMock()
        msg_result.scalars.return_value.first.return_value = message
        conv_result = MagicMock()
        conv_result.scalars.return_value.first.return_value = SimpleNamespace(
            channel="webchat", channel_conversation_id="someone-else"
        )
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[msg_result, conv_result])
        db.flush = AsyncMock()

        out = await mark_message_read(db, "m1", visitor_id="attacker")
        assert out is None
        assert message.read_at is None
        db.flush.assert_not_awaited()

    async def test_own_message_marked(self) -> None:
        from desk.channels.webchat import mark_message_read
        from desk.models.message import Message

        message = Message(content="hi", sender_type="customer", channel_message_id="m1")
        msg_result = MagicMock()
        msg_result.scalars.return_value.first.return_value = message
        conv_result = MagicMock()
        conv_result.scalars.return_value.first.return_value = SimpleNamespace(
            channel="webchat", channel_conversation_id="visitor-ok"
        )
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[msg_result, conv_result])
        db.flush = AsyncMock()

        out = await mark_message_read(db, "m1", visitor_id="visitor-ok")
        assert out is message
        assert message.read_at is not None


class TestGenericErrorFrame:
    """#26: routing errors must not echo internal exception text."""

    def test_error_frame_is_generic(self) -> None:
        import json as json_mod

        from fastapi.testclient import TestClient

        from desk.channels.webchat import _sign_visitor_token
        from desk.main import app

        with (
            patch(
                "desk.channels.webchat.route_webchat_message",
                new=AsyncMock(side_effect=RuntimeError("asyncpg: relation secret_table")),
            ),
            patch("desk.channels.webchat.AsyncSessionLocal") as session_cls,
            patch("desk.channels.webchat.get_event_bus", return_value=MagicMock()),
        ):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=AsyncMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            session_cls.return_value = cm
            client = TestClient(app)
            token = _sign_visitor_token("visitor-err", int(time.time()) + 3600)
            with client.websocket_connect(f"/ws/chat/visitor-err?token={token}") as ws:
                ws.receive_json()  # connected
                ws.send_text("hello")
                frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == "routing_failed"
        assert "secret_table" not in json_mod.dumps(frame)
        assert "asyncpg" not in json_mod.dumps(frame)
