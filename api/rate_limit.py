from __future__ import annotations

import time
import uuid

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from api.config import Settings

# Lua script for atomic sliding-window rate limiting.
# Prunes expired entries, checks count, and only adds if under limit.
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local window_start = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local member = ARGV[5]

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return 1
"""


async def check_rate_limit(
    api_key: str,
    redis: aioredis.Redis,
    settings: Settings,
) -> None:
    """
    Sliding-window rate limiter using Redis sorted sets.

    Uses a Lua script for atomic check-and-add to prevent race conditions.
    Each request is a member scored by its Unix timestamp.
    """
    if not settings.rate_limit_enabled:
        return

    now = time.time()
    window_start = now - settings.rate_limit_window_seconds
    key = f"rlm:ratelimit:{api_key}"
    member = f"{now}:{uuid.uuid4().hex[:8]}"

    allowed = await redis.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        str(window_start),
        str(now),
        str(settings.rate_limit_requests),
        str(settings.rate_limit_window_seconds + 10),
        member,
    )

    if not allowed:
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
