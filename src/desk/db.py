"""
ODW.ai Desk — Database Engine & Session Management

Provides the async SQLAlchemy engine and session factory used across
the application. FastAPI endpoints receive sessions via the `get_db`
dependency.
"""

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from desk.config import get_settings

# One engine (and thus one connection pool) per event loop. Creating an engine
# per request — the previous behavior — opened a fresh pool each time and
# exhausted PostgreSQL's connection slots under concurrent load
# (TooManyConnectionsError, found via 100-user load testing).
_engines: dict[int, AsyncEngine] = {}


def make_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from application settings."""
    settings = get_settings()
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        echo=settings.environment == "development" and settings.debug,
        future=True,
    )


def get_engine() -> AsyncEngine:
    """Return the cached async engine for the current event loop.

    A single engine (connection pool) is reused per event loop so concurrent
    requests share bounded connections instead of each opening a new pool.
    """
    try:
        loop = asyncio.get_running_loop()
        key = id(loop)
    except RuntimeError:
        key = 0
    engine = _engines.get(key)
    if engine is None:
        engine = make_engine()
        _engines[key] = engine
    return engine


async def dispose_engines() -> None:
    """Dispose all cached engines (call on application shutdown / test teardown)."""
    for engine in list(_engines.values()):
        await engine.dispose()
    _engines.clear()


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return an async sessionmaker bound to a fresh engine for the current loop."""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


def AsyncSessionLocal() -> AsyncSession:
    """Return a fresh async session bound to the current event loop."""
    return _get_session_maker()()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async database session for FastAPI dependency injection."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
