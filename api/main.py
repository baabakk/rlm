from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import __version__
from api.config import get_settings
from api.mongo_client import close_mongo, init_mongo
from api.persistence import AsyncJobStore
from api.queue import JobQueue
from api.redis_client import close_redis, init_redis
from api.routes import completions_router, health_router, jobs_router, playground_router

logger = logging.getLogger("rlm-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    settings = get_settings()

    if settings.auth_disabled:
        logger.warning("Authentication is DISABLED (RLM_AUTH_DISABLED=true)")

    # Startup
    logger.info("Initializing Redis connection...")
    redis = await init_redis(settings)

    # MongoDB (optional — disabled when RLM_MONGODB_URI is empty)
    mongo_client, mongo_db = await init_mongo(settings)
    job_store = AsyncJobStore(mongo_db) if mongo_db is not None else None

    queue = JobQueue(redis, settings, job_store=job_store)
    await queue.ensure_consumer_group()

    app.state.settings = settings
    app.state.redis = redis
    app.state.queue = queue
    app.state.mongo_db = mongo_db
    app.state.job_store = job_store

    logger.info("RLM API v%s started on port %s", __version__, settings.api_port)
    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_mongo()
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="RLM API",
        description="Production API for Recursive Language Models",
        version=__version__,
        lifespan=lifespan,
    )

    settings = get_settings()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    app.include_router(health_router)
    app.include_router(completions_router)
    app.include_router(jobs_router)
    app.include_router(playground_router)

    return app


app = create_app()
