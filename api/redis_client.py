from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import redis as sync_redis
import redis.asyncio as aioredis

from api.config import Settings


def _inject_password(url: str, password: str) -> str:
    """Inject password into a Redis URL, replacing any existing credentials."""
    parsed = urlparse(url)
    netloc = f":{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


# -- Async client (FastAPI) ---------------------------------------------------

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def init_redis(settings: Settings) -> aioredis.Redis:
    """Initialize the async Redis connection pool. Called during app lifespan."""
    global _pool, _client

    url = settings.redis_url
    if settings.redis_password:
        url = _inject_password(url, settings.redis_password)

    _pool = aioredis.ConnectionPool.from_url(
        url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )
    _client = aioredis.Redis(connection_pool=_pool)
    await _client.ping()
    return _client


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — returns the async Redis client."""
    if _client is None:
        raise RuntimeError("Redis not initialized — app lifespan not started")
    return _client


async def close_redis() -> None:
    """Shutdown: close pool and client."""
    global _pool, _client
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.disconnect()
    _client = None
    _pool = None


# -- Sync client (Worker) ----------------------------------------------------


def get_sync_redis(settings: Settings) -> sync_redis.Redis:
    """Create a synchronous Redis client for worker processes."""
    url = settings.redis_url
    if settings.redis_password:
        url = _inject_password(url, settings.redis_password)

    return sync_redis.Redis.from_url(
        url,
        max_connections=5,
        decode_responses=True,
    )
