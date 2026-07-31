"""
ODW.ai Desk — Unit Tests for WhatsApp Outbound Send

Covers the flagship outbound path:
- configured credentials -> real Meta Graph API request shape (httpx mocked)
- unconfigured credentials -> local dev stub id ("wamid.stub"), no HTTP call
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from desk.channels.base import AdapterConfig
from desk.channels.whatsapp_business import WhatsAppBusinessAdapter
from desk.config import get_settings
from desk.schemas.channels import OutboundMessage

GRAPH_BASE = "https://graph.test.invalid/v19.0"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Reset the cached Settings so per-test env overrides take effect."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_adapter() -> WhatsAppBusinessAdapter:
    config = AdapterConfig(
        adapter_id="wa-send-test",
        adapter_name="WhatsApp Send Test",
        channel_type="whatsapp_business",
    )
    # Injectable base URL keeps the test independent of the real Graph API.
    return WhatsAppBusinessAdapter(config, graph_api_base_url=GRAPH_BASE)


def _outbound() -> OutboundMessage:
    return OutboundMessage(
        conversation_id="+5511999887766",
        channel="whatsapp",
        recipient_identifier="+5511999887766",
        content="Hello from Desk",
    )


def _patch_async_client(response: MagicMock):
    """Patch httpx.AsyncClient so `async with` yields a mock client."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("desk.channels.whatsapp_business.httpx.AsyncClient", return_value=cm), mock_client


class TestWhatsAppSend:
    """Tests for WhatsAppBusinessAdapter.send()."""

    async def test_configured_send_posts_correct_graph_request(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")
        get_settings.cache_clear()
        adapter = _make_adapter()

        response = MagicMock()
        response.json = MagicMock(return_value={"messages": [{"id": "wamid.real123"}]})
        response.raise_for_status = MagicMock(return_value=None)
        patcher, mock_client = _patch_async_client(response)

        with patcher:
            result = await adapter.send(_outbound())

        assert result["success"] is True
        assert result["channel_message_id"] == "wamid.real123"

        mock_client.post.assert_awaited_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == f"{GRAPH_BASE}/1234567890/messages"
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["json"] == {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+5511999887766",
            "type": "text",
            "text": {"body": "Hello from Desk"},
        }

    async def test_configured_send_parses_first_message_id(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "42")
        get_settings.cache_clear()
        adapter = _make_adapter()

        response = MagicMock()
        response.json = MagicMock(
            return_value={"messages": [{"id": "wamid.first"}, {"id": "wamid.second"}]}
        )
        response.raise_for_status = MagicMock(return_value=None)
        patcher, _ = _patch_async_client(response)

        with patcher:
            result = await adapter.send(_outbound())

        assert result["channel_message_id"] == "wamid.first"

    async def test_unconfigured_send_returns_stub_and_skips_http(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "")
        get_settings.cache_clear()
        adapter = _make_adapter()

        with patch("desk.channels.whatsapp_business.httpx.AsyncClient") as mock_ac:
            result = await adapter.send(_outbound())

        assert result["success"] is True
        assert result["channel_message_id"] == "wamid.stub"
        mock_ac.assert_not_called()

    async def test_graph_api_error_returns_failure(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")
        get_settings.cache_clear()
        adapter = _make_adapter()

        response = MagicMock()
        response.raise_for_status = MagicMock(side_effect=RuntimeError("boom"))
        patcher, _ = _patch_async_client(response)

        with patcher:
            result = await adapter.send(_outbound())

        assert result["success"] is False
        assert result["channel_message_id"] is None
