"""
ODW.ai Desk — Database Engine & Session Management

Provides the async SQLAlchemy engine and session factory used across
the application. FastAPI endpoints receive sessions via the `get_db`
dependency.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from desk.config import get_settings


def make_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from application settings."""
    settings = get_settings()
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.environment == "development" and settings.debug,
        future=True,
    )


def get_engine() -> AsyncEngine:
    """Return a new async engine for the current event loop.

    NOTE: In production a single engine should be reused. This implementation
    creates a new engine per call to avoid event-loop binding issues in tests
    and async worker contexts. For high-throughput deployments, consider
    caching the engine in app state.
    """
    return make_engine()


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
