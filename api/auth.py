from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import Settings, get_settings
from api.redis_client import get_redis

_security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_security),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> str:
    """
    FastAPI dependency that validates the Bearer token.
    Returns the API key string on success.
    """
    token = credentials.credentials

    if settings.api_key_source == "env":
        valid_keys = {k.strip() for k in settings.api_keys.split(",") if k.strip()}
        if not valid_keys:
            # No keys configured — auth disabled (development mode)
            return token
        if token not in valid_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
    elif settings.api_key_source == "redis":
        is_member = await redis.sismember("rlm:api_keys", token)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

    return token
