"""
ODW.ai Desk — Unit Tests for Vault Client

Tests the VaultClient against the real Vault contract (INTEGRATION_CONTRACT.md §1):
POST /query with {query, top_k_chunks}, no auth, response.retrieved_chunks[].
httpx.AsyncClient is mocked; Redis cache is stubbed so no live services are needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from desk.ai.vault_client import RetrievedDocument, VaultClient


def _make_client(**kwargs) -> VaultClient:
    """Build a VaultClient with a stubbed Redis cache (no live Redis)."""
    kwargs.setdefault("vault_url", "http://localhost:8765")
    kwargs.setdefault("vault_api_key", "vk_dev_local_key")
    kwargs.setdefault("default_collection_id", "col-dev-001")
    client = VaultClient(**kwargs)
    client.cache = MagicMock()
    client.cache.get = AsyncMock(return_value=None)  # always a cache miss
    client.cache.set = AsyncMock(return_value=None)
    return client


def _patch_async_client(response: MagicMock, mock_client: MagicMock):
    """Patch httpx.AsyncClient so `async with` yields mock_client."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("desk.ai.vault_client.httpx.AsyncClient", return_value=cm)


def _mock_client_with(response: MagicMock) -> MagicMock:
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.get = AsyncMock(return_value=response)
    return mock_client


def _vault_response(retrieved_chunks: list[dict], answer: str = "Vault answer") -> MagicMock:
    """Build a mocked httpx.Response returning a real-shaped Vault payload."""
    payload = {
        "answer": answer,
        "citations": [{"marker": "[1]", "file_id": 1, "rel_path": "docs/a.md"}],
        "retrieved_chunks": retrieved_chunks,
        "metrics": {"retrieval_ms": 1.0, "generation_ms": 2.0, "total_ms": 3.0},
        "models": {"embedding": "e", "generation": "g"},
        "query_log_id": 1,
        "conversation_id": None,
    }
    response = MagicMock()
    response.json = MagicMock(return_value=payload)
    response.raise_for_status = MagicMock(return_value=None)
    response.status_code = 200
    return response


def _chunk(fused_score: float, text: str = "chunk text", rel_path: str = "docs/a.md") -> dict:
    return {
        "rank": 1,
        "chunk_id": 10,
        "file_id": 1,
        "folder_id": 2,
        "rel_path": rel_path,
        "page_start": None,
        "text": text,
        "dense_score": 0.9,
        "bm25_score": 0.8,
        "fused_score": fused_score,
    }


class TestVaultClientRetrieve:
    """Tests for VaultClient.retrieve()."""

    async def test_success_parses_retrieved_chunks(self):
        client = _make_client()
        response = _vault_response([_chunk(0.85)])
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            docs = await client.retrieve("how do I reset my password?")

        assert len(docs) == 1
        doc = docs[0]
        assert isinstance(doc, RetrievedDocument)
        assert doc.content == "chunk text"
        assert doc.score == 0.85
        assert doc.source_id == "docs/a.md"
        assert doc.metadata["chunk_id"] == 10
        assert doc.metadata["file_id"] == 1
        assert doc.metadata["answer"] == "Vault answer"
        assert doc.metadata["citations"][0]["rel_path"] == "docs/a.md"
        # to_dict keeps the stable public shape used by engine/prompt_builder
        assert set(doc.to_dict()) == {"content", "score", "source_id", "metadata"}

    async def test_posts_to_query_endpoint_without_auth(self):
        client = _make_client()
        response = _vault_response([_chunk(0.85)])
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            await client.retrieve("hello", top_k=7)

        mock_client.post.assert_awaited_once()
        _, kwargs = mock_client.post.call_args
        assert kwargs["json"] == {"query": "hello", "top_k_chunks": 7}
        # Dev default key -> no Authorization header (Vault has no auth)
        assert "Authorization" not in kwargs["headers"]

    async def test_sends_auth_header_for_real_key(self):
        client = _make_client(vault_api_key="real-secret-key")
        response = _vault_response([_chunk(0.85)])
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            await client.retrieve("hello")

        _, kwargs = mock_client.post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer real-secret-key"

    async def test_empty_retrieved_chunks_returns_empty_list(self):
        client = _make_client()
        response = _vault_response([])
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            docs = await client.retrieve("no results")

        assert docs == []

    async def test_http_status_error_returns_empty_list(self):
        client = _make_client()
        request = httpx.Request("POST", "http://localhost:8765/query")
        error_response = httpx.Response(503, request=request)
        response = MagicMock()
        response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("unavailable", request=request, response=error_response)
        )
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            docs = await client.retrieve("boom")

        assert docs == []

    async def test_generic_exception_returns_empty_list(self):
        client = _make_client()
        response = MagicMock()
        mock_client = _mock_client_with(response)
        mock_client.post = AsyncMock(side_effect=RuntimeError("connection refused"))

        with _patch_async_client(response, mock_client):
            docs = await client.retrieve("boom")

        assert docs == []

    async def test_score_filter_drops_low_confidence_chunks(self):
        client = _make_client()
        chunks = [
            _chunk(0.2, text="low score"),
            _chunk(0.5, text="kept"),
            _chunk(0.3, text="boundary kept"),
        ]
        response = _vault_response(chunks)
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            docs = await client.retrieve("filter me")

        assert [d.content for d in docs] == ["kept", "boundary kept"]


class TestVaultClientHealthCheck:
    """Tests for VaultClient.health_check()."""

    async def test_health_check_true_on_200(self):
        client = _make_client()
        response = MagicMock()
        response.status_code = 200
        mock_client = _mock_client_with(response)

        with _patch_async_client(response, mock_client):
            assert await client.health_check() is True

        # Hits GET /health
        args, _ = mock_client.get.call_args
        assert args[0] == "http://localhost:8765/health"

    async def test_health_check_false_on_exception(self):
        client = _make_client()
        response = MagicMock()
        mock_client = _mock_client_with(response)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

        with _patch_async_client(response, mock_client):
            assert await client.health_check() is False


class TestVaultClientDeleteFile:
    """Tests for VaultClient.delete_file() (V1.4 F-1, best-effort)."""

    @staticmethod
    def _delete_response(status_code: int) -> MagicMock:
        response = MagicMock()
        response.status_code = status_code
        return response

    async def test_delete_success_returns_true(self):
        client = _make_client()
        response = self._delete_response(200)
        mock_client = _mock_client_with(response)
        mock_client.delete = AsyncMock(return_value=response)

        with _patch_async_client(response, mock_client):
            assert await client.delete_file("42") is True

        # Hits DELETE {vault_url}/files/{id}
        args, kwargs = mock_client.delete.call_args
        assert args[0] == "http://localhost:8765/files/42"
        # Dev default key -> no Authorization header (Vault has no auth)
        assert "Authorization" not in kwargs["headers"]

    async def test_delete_sends_auth_header_for_real_key(self):
        client = _make_client(vault_api_key="real-secret-key")
        response = self._delete_response(204)
        mock_client = _mock_client_with(response)
        mock_client.delete = AsyncMock(return_value=response)

        with _patch_async_client(response, mock_client):
            assert await client.delete_file(7) is True

        _, kwargs = mock_client.delete.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer real-secret-key"

    async def test_delete_404_returns_false(self):
        client = _make_client()
        response = self._delete_response(404)
        mock_client = _mock_client_with(response)
        mock_client.delete = AsyncMock(return_value=response)

        with _patch_async_client(response, mock_client):
            assert await client.delete_file("missing") is False

    async def test_delete_http_error_returns_false(self):
        client = _make_client()
        response = self._delete_response(500)
        mock_client = _mock_client_with(response)
        mock_client.delete = AsyncMock(return_value=response)

        with _patch_async_client(response, mock_client):
            assert await client.delete_file("boom") is False

    async def test_delete_transport_error_returns_false_without_raising(self):
        client = _make_client()
        response = MagicMock()
        mock_client = _mock_client_with(response)
        mock_client.delete = AsyncMock(side_effect=httpx.ConnectError("down"))

        with _patch_async_client(response, mock_client):
            assert await client.delete_file("boom") is False
