from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import __version__
from api.config import get_settings
from api.queue import JobQueue
from api.redis_client import close_redis, init_redis
from api.routes import completions_router, health_router, jobs_router

logger = logging.getLogger("rlm-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    settings = get_settings()

    # Startup
    logger.info("Initializing Redis connection...")
    redis = await init_redis(settings)

    queue = JobQueue(redis, settings)
    await queue.ensure_consumer_group()

    app.state.settings = settings
    app.state.redis = redis
    app.state.queue = queue

    logger.info(f"RLM API v{__version__} started on port {settings.api_port}")
    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="RLM API",
        description="Production API for Recursive Language Models",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    app.include_router(health_router)
    app.include_router(completions_router)
    app.include_router(jobs_router)

    return app


app = create_app()
