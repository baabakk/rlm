from __future__ import annotations

import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Request

from api import __version__
from api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    redis: aioredis.Redis = request.app.state.redis
    queue = request.app.state.queue

    redis_ok = False
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        pass

    # Count active workers by heartbeats in the last 30 seconds
    active_workers = 0
    try:
        now = time.time()
        active_workers = await redis.zcount(
            "rlm:workers:heartbeat", now - 30, "+inf"
        )
    except Exception:
        pass

    pending = 0
    try:
        pending = await queue.get_pending_count()
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        version=__version__,
        redis_connected=redis_ok,
        active_workers=active_workers,
        pending_jobs=pending,
    )
