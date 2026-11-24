"""
Regression tests for full-audit round 1, batch 9 (.ocr-reports/full-audit.json).

Covers:
- #25 failed webchat send must not evict a replacement connection
- #27 inbound polling logs, degrades and restarts instead of dying silently
- #31 active-persona selection is deterministic
- #37 agent WebSocket accepts JWT principals (and fails closed outside dev)
- #38 CSAT check-and-set runs under a row lock
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from desk.config import Settings, get_settings


class TestSendFailureKeepsReplacement:
    """#25: disconnect on send failure must be socket-identity-guarded."""

    async def test_replacement_survives_failed_send(self) -> None:
        from desk.channels.webchat import WebChatManager

        manager = WebChatManager()
        old = MagicMock()
        new = MagicMock()

        async def failing_send(payload):
            # A reconnect registers the replacement while the old send fails.
            manager.active_connections["v"] = new
            raise RuntimeError("socket dead")

        old.send_json = AsyncMock(side_effect=failing_send)
        manager.active_connections["v"] = old

        delivered = await manager.send_to_visitor("v", {"type": "message"})
        assert delivered is False
        assert manager.active_connections["v"] is new


class TestPollingRestart:
    """#27: one receive() error must not kill inbound polling forever."""

    async def test_poll_restarts_after_error(self) -> None:
        from desk.channels.base import AdapterConfig
        from desk.channels.manager import ChannelAdapterManager

        adapter = MagicMock()
        adapter.config = AdapterConfig(
            adapter_id="poll-1", adapter_name="P", channel_type="mock", enabled=True
        )
        calls = {"n": 0}
        message = MagicMock()
        message.model_dump.return_value = {"content": "hi"}

        async def receive():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient blip")
            yield message

        adapter.receive = receive
        manager = ChannelAdapterManager(MagicMock(), MagicMock())
        manager.event_bus.publish = AsyncMock()
        manager.register(adapter)

        with patch("asyncio.sleep", new=AsyncMock()):
            await manager.start_inbound_polling()

        assert calls["n"] == 2
        manager.event_bus.publish.assert_awaited_once()
        adapter.update_health.assert_called()
        assert adapter.update_health.call_args.args[0] == "degraded"


class TestPersonaDeterministic:
    """#31: active persona query must order deterministically."""

    async def test_query_orders_by_updated_at_desc(self) -> None:
        from desk.persona.service import PersonaService

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        await PersonaService(db).get_active_persona()
        query = db.execute.await_args.args[0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
        assert "ORDER BY" in compiled
        assert "updated_at DESC" in compiled


def _ws(token: str | None) -> MagicMock:
    ws = MagicMock()
    ws.query_params = {"token": token} if token else {}
    ws.headers.get = lambda key, default=None: default
    return ws


def _agent_jwt() -> str:
    now = int(time.time())
    return jose_jwt.encode(
        {"sub": str(uuid4()), "role": "agent", "iat": now, "exp": now + 600},
        get_settings().secret_key,
        algorithm="HS256",
    )


class TestWebsocketJwt:
    """#37: JWT principals reach the agent socket; fail closed outside dev."""

    def test_jwt_accepted_with_key_set(self) -> None:
        from desk.agents.websocket import _websocket_authenticated

        settings = Settings(desk_api_key="shared-key")
        with patch("desk.agents.websocket.get_settings", return_value=settings):
            assert _websocket_authenticated(_ws(_agent_jwt())) is True

    def test_wrong_token_rejected(self) -> None:
        from desk.agents.websocket import _websocket_authenticated

        settings = Settings(desk_api_key="shared-key")
        with patch("desk.agents.websocket.get_settings", return_value=settings):
            assert _websocket_authenticated(_ws("not-the-key")) is False

    def test_shared_key_still_accepted(self) -> None:
        from desk.agents.websocket import _websocket_authenticated

        settings = Settings(desk_api_key="shared-key")
        with patch("desk.agents.websocket.get_settings", return_value=settings):
            assert _websocket_authenticated(_ws("shared-key")) is True

    def test_no_key_production_requires_jwt(self) -> None:
        from desk.agents.websocket import _websocket_authenticated

        settings = Settings(environment="production", secret_key="a" * 64, desk_api_key="")
        now = int(time.time())
        token = jose_jwt.encode(
            {"sub": str(uuid4()), "role": "agent", "iat": now, "exp": now + 600},
            settings.secret_key,
            algorithm="HS256",
        )
        with patch("desk.agents.websocket.get_settings", return_value=settings):
            assert _websocket_authenticated(_ws(None)) is False
            assert _websocket_authenticated(_ws(token)) is True

    def test_no_key_development_open(self) -> None:
        from desk.agents.websocket import _websocket_authenticated

        settings = Settings(environment="development", desk_api_key="")
        with patch("desk.agents.websocket.get_settings", return_value=settings):
            assert _websocket_authenticated(_ws(None)) is True


class TestCsatRowLock:
    """#38: the CSAT check-and-set must lock the conversation row."""

    async def test_submission_locks_row(self) -> None:
        from desk.surveys.csat_api import CSATSubmission, submit_csat

        result = MagicMock()
        result.scalar_one_or_none.return_value = None  # 404 path, after the query
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        with pytest.raises(HTTPException) as exc:
            await submit_csat(uuid4(), CSATSubmission(score=5), db)
        assert exc.value.status_code == 404
        query = db.execute.await_args.args[0]
        assert query._for_update_arg is not None
