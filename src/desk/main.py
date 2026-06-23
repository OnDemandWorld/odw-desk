"""
ODW.ai Desk — FastAPI Application Entry Point

Self-hosted, WhatsApp-first AI customer support agent.
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from desk.channels.base import AdapterConfig
from desk.channels.manager import ChannelAdapterManager
from desk.channels.mock import MockChannelAdapter
from desk.config import get_settings
from desk.events.redis_streams import RedisStreamsEventBus
from desk.utils.redis_client import get_redis_manager

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events: startup and shutdown."""
    settings = get_settings()
    logger.info(
        "Starting ODW.ai Desk",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize Redis connection (INFRA-003)
    redis_manager = get_redis_manager()
    await redis_manager.connect()
    app.state.redis_manager = redis_manager

    # Initialize event bus (INFRA-004)
    event_bus = RedisStreamsEventBus(redis_manager)
    await event_bus.connect()
    app.state.event_bus = event_bus

    # Initialize channel adapter manager (INFRA-006)
    channel_manager = ChannelAdapterManager(event_bus, redis_manager)
    app.state.channel_manager = channel_manager

    # Register mock adapter for development/testing
    mock_config = AdapterConfig(
        adapter_id="mock-001",
        adapter_name="Mock Channel",
        channel_type="mock",
    )
    mock_adapter = MockChannelAdapter(mock_config)
    channel_manager.register(mock_adapter)
    await channel_manager.start_all()

    logger.info("Redis, event bus, and channel adapter manager initialized")

    yield

    logger.info("Shutting down ODW.ai Desk")
    # Graceful shutdown of all services
    await channel_manager.stop_all()
    await event_bus.disconnect()
    await redis_manager.disconnect()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="ODW.ai Desk",
        description="Self-hosted, WhatsApp-first AI customer support agent",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # TODO: Include routers (CORE-001, AGENT-001, etc.)
    # app.include_router(whatsapp_router)
    # app.include_router(webchat_router)
    # app.include_router(agent_router)
    # app.include_router(admin_router)

    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        Health check endpoint for load balancers and Kubernetes probes.

        Returns:
            dict: Health status
        """
        # Check Redis connectivity (INFRA-003)
        redis_health = await get_redis_manager().health_check()

        overall_status = "healthy"
        if redis_health["status"] != "healthy":
            overall_status = "degraded"

        return {
            "status": overall_status,
            "version": settings.app_version,
            "environment": settings.environment,
            "redis": redis_health,
            "components": {
                "database": "pending",  # INFRA-002
                "event_bus": "healthy",  # Connected on startup
                "channel_gateway": "healthy",  # Mock adapter registered
            },
        }

    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "ODW.ai Desk",
            "version": settings.app_version,
            "docs": "/docs" if settings.environment != "production" else None,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "desk.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
