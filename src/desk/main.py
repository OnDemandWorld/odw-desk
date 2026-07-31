"""
ODW.ai Desk — FastAPI Application Entry Point

Self-hosted, WhatsApp-first AI customer support agent.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from desk.admin.api import router as admin_router
from desk.admin.persona_policy_api import router as persona_policy_router
from desk.agents.inbox_api import router as agent_router
from desk.agents.websocket import router as websocket_router
from desk.ai.engine import AIEngine
from desk.channels.base import AdapterConfig
from desk.channels.manager import ChannelAdapterManager
from desk.channels.mock import MockChannelAdapter
from desk.channels.outbound import OutboundDispatcher
from desk.channels.whatsapp_business import get_adapter as get_whatsapp_adapter
from desk.channels.whatsapp_business import router as whatsapp_router
from desk.config import get_settings
from desk.db import get_engine
from desk.events.redis_streams import RedisStreamsEventBus
from desk.security.api_auth import require_api_key
from desk.utils.redis_client import get_redis_manager
from desk.workers.message_processor import MessageProcessor

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
        enabled=True,
    )
    mock_adapter = MockChannelAdapter(mock_config)
    channel_manager.register(mock_adapter)

    # Register WhatsApp Business API adapter for outbound delivery
    whatsapp_adapter = get_whatsapp_adapter()
    if whatsapp_adapter:
        channel_manager.register(whatsapp_adapter)
        logger.info("WhatsApp Business adapter registered")

    await channel_manager.start_all()

    # Start message processor worker in the background
    outbound_dispatcher = OutboundDispatcher(channel_manager)
    ai_engine = AIEngine()
    processor = MessageProcessor(event_bus, outbound_dispatcher, ai_engine)
    processor_task = asyncio.create_task(processor.run(), name="message-processor")

    logger.info("Redis, event bus, channel adapter manager, and message processor initialized")

    yield

    logger.info("Shutting down ODW.ai Desk")
    # Cancel message processor worker
    processor_task.cancel()
    try:
        await processor_task
    except asyncio.CancelledError:
        logger.info("Message processor worker cancelled")

    # Graceful shutdown of all services
    await channel_manager.stop_all()
    await event_bus.disconnect()
    await redis_manager.disconnect()
    await get_engine().dispose()


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

    # Optional API key guard for admin + agent inbox routes. When DESK_API_KEY is
    # unset the dependency is a no-op, so routes stay open (backward compatible).
    # Health (/health) and webhooks (/api/v1/webhooks/*) are intentionally NOT guarded.
    api_guard = [Depends(require_api_key)]

    # Include routers (CORE-001, AGENT-001, etc.)
    app.include_router(whatsapp_router)
    app.include_router(agent_router, dependencies=api_guard)
    app.include_router(websocket_router)
    app.include_router(admin_router, dependencies=api_guard)
    app.include_router(persona_policy_router, dependencies=api_guard)
    # app.include_router(webchat_router)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """
        Health check endpoint for load balancers and Kubernetes probes.

        Returns:
            dict: Health status
        """
        # Check Redis connectivity (INFRA-003)
        redis_health = await get_redis_manager().health_check()

        # Check database connectivity (INFRA-002)
        db_health = {"status": "healthy"}
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                result.scalar()
        except Exception as exc:  # noqa: BLE001
            db_health = {"status": "unhealthy", "error": str(exc)}

        overall_status = "healthy"
        if redis_health["status"] != "healthy" or db_health["status"] != "healthy":
            overall_status = "degraded"

        return {
            "status": overall_status,
            "version": settings.app_version,
            "environment": settings.environment,
            "redis": redis_health,
            "database": db_health,
            "components": {
                "database": db_health["status"],
                "event_bus": "healthy",  # Connected on startup
                "channel_gateway": "healthy",  # Mock adapter registered
            },
        }

    @app.get("/", tags=["Root"])
    async def root() -> dict:
        """Root endpoint with API information."""
        return {
            "name": "ODW.ai Desk",
            "version": settings.app_version,
            "docs": "/docs" if settings.environment != "production" else None,
        }

    @app.get("/metrics", tags=["Observability"])
    async def metrics() -> Response:
        """
        Prometheus metrics endpoint.

        Exposes all counters/gauges/histograms defined in
        ``desk.observability.metrics`` in the Prometheus text exposition format.
        """
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

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
