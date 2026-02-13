from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.auth import verify_api_key
from api.models import CompletionResultResponse, JobResultResponse, JobStatus
from api.redis_client import get_redis

router = APIRouter(prefix="/v1", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobResultResponse)
async def get_job(
    job_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key),
) -> JobResultResponse:
    """Poll for job status and result."""
    queue = request.app.state.queue
    job_data = await queue.get_job_status(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    result = None
    if job_data.get("status") == JobStatus.COMPLETED.value:
        result_data = await queue.get_job_result(job_id)
        if result_data:
            result = CompletionResultResponse(**result_data)

    return JobResultResponse(
        job_id=job_id,
        status=JobStatus(job_data["status"]),
        created_at=job_data["created_at"],
        started_at=job_data.get("started_at"),
        completed_at=job_data.get("completed_at"),
        result=result,
        error=job_data.get("error"),
        current_iteration=int(job_data.get("current_iteration", 0)),
        max_iterations=int(job_data.get("max_iterations", 30)),
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key),
    redis: aioredis.Redis = Depends(get_redis),
) -> StreamingResponse:
    """
    SSE stream of real-time iteration events for a job.

    Event types: started, metadata, iteration, completed, failed.
    Stream closes after a terminal event (completed / failed).
    """
    queue = request.app.state.queue
    job_data = await queue.get_job_status(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    # If already terminal, return the final event immediately
    if job_data["status"] in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):

        async def terminal_stream():
            if job_data["status"] == JobStatus.COMPLETED.value:
                result = await queue.get_job_result(job_id)
                yield f"event: completed\ndata: {json.dumps(result or {})}\n\n"
            else:
                error = job_data.get("error", "Unknown error")
                yield f"event: failed\ndata: {json.dumps({'error': error})}\n\n"

        return StreamingResponse(
            terminal_stream(),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    # Subscribe to the job's Pub/Sub channel for live events
    async def event_stream():
        pubsub = redis.pubsub()
        channel = f"rlm:job:{job_id}:events"
        await pubsub.subscribe(channel)

        try:
            yield ": connected\n\n"

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=30.0
                )

                if message and message["type"] == "message":
                    event_data = json.loads(message["data"])
                    event_type = event_data.get("event_type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

                    if event_type in ("completed", "failed"):
                        break
                else:
                    # Keepalive comment to prevent proxy timeouts
                    yield ": keepalive\n\n"

                    # Fallback: check if job finished while we waited
                    current = await queue.get_job_status(job_id)
                    if current and current.get("status") in (
                        JobStatus.COMPLETED.value,
                        JobStatus.FAILED.value,
                    ):
                        if current["status"] == JobStatus.COMPLETED.value:
                            result = await queue.get_job_result(job_id)
                            yield f"event: completed\ndata: {json.dumps(result or {})}\n\n"
                        else:
                            error = current.get("error", "Unknown error")
                            yield f"event: failed\ndata: {json.dumps({'error': error})}\n\n"
                        break

                # Yield control to the event loop
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
