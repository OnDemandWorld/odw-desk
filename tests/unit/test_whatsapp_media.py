"""
ODW.ai Desk — Unit Tests for WhatsApp Media Handling (F7)

Covers:
- inbound media parsing (image/document -> media_id / mime_type / caption)
- resolve_media_url (Graph GET {base}/{media_id} -> {url}), mock httpx
- send_media request shape (mock httpx) + unconfigured fallback
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from desk.channels.base import AdapterConfig
from desk.channels.whatsapp_business import WhatsAppBusinessAdapter
from desk.config import get_settings

GRAPH_BASE = "https://graph.test.invalid/v19.0"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Reset the cached Settings so per-test env overrides take effect."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_adapter() -> WhatsAppBusinessAdapter:
    config = AdapterConfig(
        adapter_id="wa-media-test",
        adapter_name="WhatsApp Media Test",
        channel_type="whatsapp_business",
    )
    return WhatsAppBusinessAdapter(config, graph_api_base_url=GRAPH_BASE)


def _patch_async_client(response: MagicMock):
    """Patch httpx.AsyncClient so `async with` yields a mock client (get+post)."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.get = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("desk.channels.whatsapp_business.httpx.AsyncClient", return_value=cm), mock_client


def _media_payload(msg_type: str, media: dict) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "id": "wamid.media1",
                                    "from": "+5511999887766",
                                    "type": msg_type,
                                    msg_type: media,
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


class TestInboundMediaParsing:
    def test_parse_image_message_extracts_media_metadata(self):
        adapter = _make_adapter()
        payload = _media_payload(
            "image", {"id": "media-img-1", "mime_type": "image/jpeg", "caption": "see this"}
        )

        messages = adapter.parse_inbound_message(payload)

        assert len(messages) == 1
        msg = messages[0]
        assert msg.metadata["message_type"] == "image"
        assert msg.metadata["media_type"] == "image"
        assert msg.metadata["media_id"] == "media-img-1"
        assert msg.metadata["mime_type"] == "image/jpeg"
        assert msg.metadata["caption"] == "see this"
        # Caption becomes the textual content when present.
        assert msg.content == "see this"

    def test_parse_document_without_caption_uses_placeholder(self):
        adapter = _make_adapter()
        payload = _media_payload(
            "document", {"id": "media-doc-9", "mime_type": "application/pdf"}
        )

        messages = adapter.parse_inbound_message(payload)

        msg = messages[0]
        assert msg.metadata["media_id"] == "media-doc-9"
        assert msg.metadata["mime_type"] == "application/pdf"
        assert msg.metadata["caption"] is None
        assert msg.content == "[document]"


class TestResolveMediaUrl:
    async def test_resolve_media_url_returns_graph_url(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
        get_settings.cache_clear()
        adapter = _make_adapter()

        response = MagicMock()
        response.json = MagicMock(return_value={"url": "https://lookaside.invalid/x.jpg"})
        response.raise_for_status = MagicMock(return_value=None)
        patcher, mock_client = _patch_async_client(response)

        with patcher:
            url = await adapter.resolve_media_url("media-img-1")

        assert url == "https://lookaside.invalid/x.jpg"
        mock_client.get.assert_awaited_once()
        args, kwargs = mock_client.get.call_args
        assert args[0] == f"{GRAPH_BASE}/media-img-1"
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"

    async def test_resolve_media_url_unconfigured_returns_none(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "")
        get_settings.cache_clear()
        adapter = _make_adapter()

        with patch("desk.channels.whatsapp_business.httpx.AsyncClient") as mock_ac:
            assert await adapter.resolve_media_url("media-img-1") is None
        mock_ac.assert_not_called()


class TestSendMedia:
    async def test_configured_send_media_posts_correct_graph_request(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")
        get_settings.cache_clear()
        adapter = _make_adapter()

        response = MagicMock()
        response.json = MagicMock(return_value={"messages": [{"id": "wamid.media.real"}]})
        response.raise_for_status = MagicMock(return_value=None)
        patcher, mock_client = _patch_async_client(response)

        with patcher:
            result = await adapter.send_media(
                "+5511999887766", "image", "https://cdn.invalid/x.jpg", caption="hi"
            )

        assert result["success"] is True
        assert result["channel_message_id"] == "wamid.media.real"

        mock_client.post.assert_awaited_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == f"{GRAPH_BASE}/1234567890/messages"
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert kwargs["json"] == {
            "messaging_product": "whatsapp",
            "to": "+5511999887766",
            "type": "image",
            "image": {"link": "https://cdn.invalid/x.jpg"},
            "caption": "hi",
        }

    async def test_send_media_without_caption_omits_caption_key(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "42")
        get_settings.cache_clear()
        adapter = _make_adapter()

        response = MagicMock()
        response.json = MagicMock(return_value={"messages": [{"id": "wamid.doc"}]})
        response.raise_for_status = MagicMock(return_value=None)
        patcher, mock_client = _patch_async_client(response)

        with patcher:
            await adapter.send_media("+5511999887766", "document", "https://cdn.invalid/f.pdf")

        _, kwargs = mock_client.post.call_args
        assert "caption" not in kwargs["json"]
        assert kwargs["json"]["document"] == {"link": "https://cdn.invalid/f.pdf"}

    async def test_unconfigured_send_media_returns_stub_and_skips_http(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "")
        get_settings.cache_clear()
        adapter = _make_adapter()

        with patch("desk.channels.whatsapp_business.httpx.AsyncClient") as mock_ac:
            result = await adapter.send_media("+5511999887766", "image", "https://cdn.invalid/x.jpg")

        assert result["success"] is True
        assert result["channel_message_id"] == "wamid.stub"
        mock_ac.assert_not_called()
