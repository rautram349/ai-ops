"""FastAPI application factory.

Import ``app`` to mount it directly (e.g. with uvicorn), or call
``create_app()`` to get a fresh instance (useful in tests).

Usage::

    uvicorn backend.app:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.approvals import router as approvals_router
from backend.api.chat import router as chat_router
from backend.api.conversations import router as conversations_router
from backend.api.health import router as health_router
from backend.api.incidents import router as incidents_router
from backend.api.monitor import router as monitor_router
from backend.core.config import settings
from backend.core.logging import configure_logging
from backend.scheduler import start_scheduler, stop_scheduler

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: configure logging, start scheduler on startup."""
    configure_logging(settings.log_level)
    logger.info(
        "startup",
        host=settings.backend_host,
        port=settings.backend_port,
        log_level=settings.log_level,
    )
    await start_scheduler()
    yield
    await stop_scheduler()
    logger.info("shutdown")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Returns:
        A fully configured ``FastAPI`` instance.
    """
    application = FastAPI(
        title="E-commerce Operations Brain",
        description=(
            "AI-powered operations co-pilot: diagnoses business incidents, "
            "proposes corrective actions, and manages human-in-the-loop approvals."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(health_router)
    application.include_router(chat_router)
    application.include_router(conversations_router)
    application.include_router(approvals_router)
    application.include_router(incidents_router)

    application.include_router(monitor_router)


    return application


app: FastAPI = create_app()
