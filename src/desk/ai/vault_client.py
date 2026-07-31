"""
ODW.ai Desk — Vault Client (AI-003)

Queries ODW.ai Vault's RAG query API for relevant knowledge base chunks.
Caches results in Redis for performance.

Vault contract (see INTEGRATION_CONTRACT.md §1):
- Base URL: http://127.0.0.1:8765
- No authentication (do NOT send an Authorization header unless a real key is set)
- Retrieval: POST /query  body {query, top_k_chunks, folder_filter?}
- Health:    GET  /health -> {ollama, chroma, database, fasttext}
"""

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from desk.utils.redis_client import Cache, get_redis_manager

logger = structlog.get_logger()

# Vault ships with no auth. This is the dev placeholder key Desk historically
# configured; when the key is empty or equals this default we send no header.
_DEV_DEFAULT_API_KEY = "vk_dev_local_key"

# Minimum fused_score for a retrieved chunk to be kept.
_MIN_SCORE = 0.3


@dataclass
class RetrievedDocument:
    """A document retrieved from Vault."""

    content: str
    score: float
    source_id: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "score": self.score,
            "source_id": self.source_id,
            "metadata": self.metadata,
        }


class VaultClient:
    """
    Client for querying ODW.ai Vault knowledge base.

    Implements caching with Redis and result ranking.
    """

    def __init__(
        self,
        vault_url: str,
        vault_api_key: str,
        default_collection_id: str,
        cache_ttl_seconds: int = 600,  # 10 minutes
        collection_folder_map: dict[str, dict[str, Any]] | None = None,
    ):
        """
        Initialize Vault Client.

        Args:
            vault_url: Vault API base URL
            vault_api_key: Vault API authentication key (Vault has no auth; the
                header is only sent when a real, non-default key is configured)
            default_collection_id: Default knowledge base collection ID
            cache_ttl_seconds: Cache TTL in seconds (default: 10 minutes)
            collection_folder_map: Optional mapping of collection_id -> Vault
                folder_filter dict (e.g. {"folder_id": 1} or {"path_prefix": "..."}).
                When a collection has an entry, its folder_filter is sent to Vault.
        """
        self.vault_url = vault_url.rstrip("/")
        self.vault_api_key = vault_api_key
        self.default_collection_id = default_collection_id
        self.cache_ttl_seconds = cache_ttl_seconds
        self.collection_folder_map = collection_folder_map or {}

        # Initialize Redis cache
        redis_manager = get_redis_manager()
        self.cache = Cache(redis_manager, "vault")

        logger.info(
            "Vault Client initialized",
            vault_url=vault_url,
            collection_id=default_collection_id,
            cache_ttl=cache_ttl_seconds,
        )

    def _auth_headers(self) -> dict[str, str]:
        """Build request headers, only adding Authorization for a real key."""
        headers = {"Content-Type": "application/json"}
        if self.vault_api_key and self.vault_api_key != _DEV_DEFAULT_API_KEY:
            headers["Authorization"] = f"Bearer {self.vault_api_key}"
        return headers

    def _cache_key(self, collection_id: str, query: str, top_k: int) -> str:
        """Generate cache key for a retrieval query."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"{collection_id}:{query_hash}:{top_k}"

    async def retrieve(
        self,
        query: str,
        collection_id: str | None = None,
        top_k: int = 5,
    ) -> list[RetrievedDocument]:
        """
        Retrieve relevant documents from Vault.

        Args:
            query: Search query
            collection_id: Collection ID (defaults to configured default)
            top_k: Number of top results to return

        Returns:
            List of retrieved documents sorted by relevance score
        """
        collection = collection_id or self.default_collection_id

        # Check cache first
        cache_key = self._cache_key(collection, query, top_k)
        cached_result = await self.cache.get(cache_key)
        if cached_result is not None and isinstance(cached_result, list):
            logger.debug("Vault cache hit", query=query[:50], collection=collection)
            return [RetrievedDocument(**doc) for doc in cached_result]

        # Cache miss, query Vault API
        try:
            payload: dict[str, Any] = {
                "query": query,
                "top_k_chunks": top_k,
            }
            folder_filter = self.collection_folder_map.get(collection)
            if folder_filter:
                payload["folder_filter"] = folder_filter

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.vault_url}/query",
                    headers=self._auth_headers(),
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

            answer = result.get("answer", "")
            citations = result.get("citations", [])

            # Parse retrieved_chunks into the stable RetrievedDocument interface
            documents = []
            for chunk in result.get("retrieved_chunks", []):
                score = float(chunk.get("fused_score", 0.0) or 0.0)
                documents.append(
                    RetrievedDocument(
                        content=chunk.get("text", ""),
                        score=score,
                        source_id=str(chunk.get("rel_path") or chunk.get("file_id") or ""),
                        metadata={
                            "chunk_id": chunk.get("chunk_id"),
                            "file_id": chunk.get("file_id"),
                            "folder_id": chunk.get("folder_id"),
                            "rel_path": chunk.get("rel_path"),
                            "page_start": chunk.get("page_start"),
                            "dense_score": chunk.get("dense_score"),
                            "bm25_score": chunk.get("bm25_score"),
                            "answer": answer,
                            "citations": citations,
                        },
                    )
                )

            # Filter low-confidence results (fused_score < 0.3)
            documents = [doc for doc in documents if doc.score >= _MIN_SCORE]

            # Cache the results
            await self.cache.set(
                cache_key,
                [doc.to_dict() for doc in documents],
                ttl_seconds=self.cache_ttl_seconds,
            )

            logger.info(
                "Vault retrieval complete",
                query=query[:50],
                collection=collection,
                documents=len(documents),
                cached=True,
            )

            return documents

        except httpx.HTTPStatusError as e:
            logger.error(
                "Vault API error",
                status_code=e.response.status_code,
                error=e.response.text,
            )
            return []
        except Exception as e:
            logger.error("Vault retrieval failed", error=str(e), query=query[:50])
            return []

    async def health_check(self) -> bool:
        """Check if Vault API is reachable (GET /health, True on HTTP 200)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.vault_url}/health",
                    headers=self._auth_headers(),
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("Vault health check failed", error=str(e))
            return False


# Global instance
_vault_client: VaultClient | None = None


def get_vault_client() -> VaultClient:
    """Get or create global Vault Client instance."""
    global _vault_client
    if _vault_client is None:
        from desk.config import get_settings

        settings = get_settings()
        _vault_client = VaultClient(
            vault_url=settings.vault_url,
            vault_api_key=settings.vault_api_key,
            default_collection_id=settings.vault_collection_id,
        )
    return _vault_client
