"""
ODW.ai Desk — Redis Connection Manager

Manages Redis connection pool and provides a cached client instance.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

import redis.asyncio as redis
from redis.asyncio import Redis

from desk.config import Settings, get_settings


class RedisConnectionManager:
    """
    Redis connection manager with connection pooling.

    Provides health checks and a cached connection pool for the application.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._pool: redis.Redis | None = None

    async def connect(self) -> Redis:
        """Create or return existing Redis connection pool."""
        if self._pool is None:
            self._pool = redis.from_url(
                str(self.settings.redis_url),
                decode_responses=True,
                max_connections=50,
            )
        return self._pool

    async def disconnect(self) -> None:
        """Close Redis connection pool."""
        if self._pool is not None:
            await self._pool.aclose()  # close() is deprecated since redis-py 5.0.1
            self._pool = None

    async def health_check(self) -> dict:
        """Check Redis connectivity."""
        try:
            client = await self.connect()
            ping_response = await client.ping()
            info = await client.info("server")
            return {
                "status": "healthy",
                "ping": ping_response,
                "redis_version": info.get("redis_version", "unknown"),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    @asynccontextmanager
    async def get_client(self) -> AsyncGenerator[Redis, None]:
        """Get a Redis client from the pool as an async context manager."""
        # A failed command (timeout, blip) must not tear down the process-wide
        # pool: other coroutines still hold clients from it. Reconnection is
        # handled lazily by connect() on the next acquisition.
        client = await self.connect()
        yield client


@lru_cache
def get_redis_manager() -> RedisConnectionManager:
    """Get cached Redis connection manager."""
    return RedisConnectionManager(get_settings())


class Cache:
    """
    Generic cache abstraction layer using Redis.

    Provides get/set/delete operations with JSON serialization and TTL support.
    """

    def __init__(self, redis_manager: RedisConnectionManager, prefix: str = "desk:"):
        self.redis_manager = redis_manager
        self.prefix = prefix

    def _key(self, key: str) -> str:
        """Construct prefixed cache key."""
        return f"{self.prefix}{key}"

    async def get(self, key: str) -> object | None:
        """
        Get a value from cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            Deserialized value, or None if not found/expired
        """
        async with self.redis_manager.get_client() as client:
            value = await client.get(self._key(key))
            if value is None:
                return None
            result: object = json.loads(value)
            return result

    async def set(
        self,
        key: str,
        value: object,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Set a value in cache.

        Args:
            key: Cache key (without prefix)
            value: Value to serialize and store
            ttl_seconds: Optional TTL in seconds
        """
        async with self.redis_manager.get_client() as client:
            serialized = json.dumps(value)
            await client.set(self._key(key), serialized, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        """Delete a value from cache."""
        async with self.redis_manager.get_client() as client:
            await client.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        async with self.redis_manager.get_client() as client:
            return await client.exists(self._key(key)) > 0


# Cache key pattern generators (TSD §7)

def customer_key(channel: str, identifier: str) -> str:
    """
    Generate cache key for customer lookup.

    Pattern: `customer:{channel}:{sha256(identifier)}`
    """
    import hashlib

    identifier_hash = hashlib.sha256(identifier.encode()).hexdigest()[:32]
    return f"customer:{channel}:{identifier_hash}"


def vault_key(collection_id: str, query_hash: str) -> str:
    """
    Generate cache key for Vault query results.

    Pattern: `vault:{collection}:{query_hash}`
    """
    return f"vault:{collection_id}:{query_hash}"


def context_key(conversation_id: str) -> str:
    """
    Generate cache key for conversation context.

    Pattern: `context:{conversation_id}`
    """
    return f"context:{conversation_id}"


def ai_config_key(deployment_id: str) -> str:
    """
    Generate cache key for AI configuration.

    Pattern: `ai_config:{deployment_id}`
    """
    return f"ai_config:{deployment_id}"


def session_key(session_id: str) -> str:
    """
    Generate cache key for web chat session.

    Pattern: `session:{session_id}`
    """
    return f"session:{session_id}"


async def get_cache() -> Cache:
    """Get global cache instance."""
    return Cache(get_redis_manager(), prefix=get_settings().redis_prefix)
