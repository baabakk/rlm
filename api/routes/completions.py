from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request

from api.auth import verify_api_key
from api.config import Settings, get_settings
from api.models import CompletionRequest, CompletionResponse, JobStatus
from api.rate_limit import check_rate_limit
from api.redis_client import get_redis

router = APIRouter(prefix="/v1", tags=["completions"])


@router.post("/completions", response_model=CompletionResponse, status_code=202)
async def create_completion(
    body: CompletionRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> CompletionResponse:
    """Enqueue a new RLM completion job. Returns immediately with a job_id."""
    await check_rate_limit(api_key, redis, settings)

    queue = request.app.state.queue
    job_id = await queue.enqueue(body, api_key)

    return CompletionResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc),
    )
