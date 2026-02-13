from __future__ import annotations

import time

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from api.config import Settings


async def check_rate_limit(
    api_key: str,
    redis: aioredis.Redis,
    settings: Settings,
) -> None:
    """
    Sliding-window rate limiter using Redis sorted sets.

    Each request is a member scored by its Unix timestamp.
    Expired members (outside the window) are pruned on every check.
    """
    if not settings.rate_limit_enabled:
        return

    now = time.time()
    window_start = now - settings.rate_limit_window_seconds
    key = f"rlm:ratelimit:{api_key}"

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)  # prune expired
    pipe.zcard(key)  # count current
    pipe.zadd(key, {f"{now}": now})  # add this request
    pipe.expire(key, settings.rate_limit_window_seconds + 10)
    results = await pipe.execute()

    current_count = results[1]

    if current_count >= settings.rate_limit_requests:
        # Remove the entry we just added since we're rejecting
        await redis.zrem(key, f"{now}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded. "
                f"Max {settings.rate_limit_requests} requests "
                f"per {settings.rate_limit_window_seconds}s."
            ),
            headers={
                "Retry-After": str(settings.rate_limit_window_seconds),
                "X-RateLimit-Limit": str(settings.rate_limit_requests),
                "X-RateLimit-Remaining": "0",
            },
        )
