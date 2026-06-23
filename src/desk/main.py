"""
ODW.ai Desk — FastAPI Application Entry Point

Self-hosted, WhatsApp-first AI customer support agent.
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from desk.config import get_settings

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

    # TODO: Initialize database connections (INFRA-002)
    # TODO: Initialize Redis connection (INFRA-003)
    # TODO: Initialize event bus (INFRA-004)
    # TODO: Start channel adapters (CORE-001, CORE-002, CORE-003)

    yield

    logger.info("Shutting down ODW.ai Desk")
    # TODO: Graceful shutdown of all services


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
        # TODO: Check database connectivity (INFRA-002)
        # TODO: Check Redis connectivity (INFRA-003)
        # TODO: Check event bus connectivity (INFRA-004)
        # TODO: Check channel adapter health (CORE-001, CORE-002, CORE-003)

        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
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
