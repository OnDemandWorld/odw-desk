"""
ODW.ai Desk — FastAPI Dependency Injection

Common dependencies used by FastAPI route handlers.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from desk.db import get_db as _get_db
from desk.events.redis_streams import RedisStreamsEventBus
from desk.utils.redis_client import get_redis_manager


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async for session in _get_db():
        yield session


def get_event_bus() -> RedisStreamsEventBus:
    """Return the shared Redis Streams event bus."""
    return RedisStreamsEventBus(get_redis_manager())
