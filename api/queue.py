from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from api.config import Settings
from api.models import CompletionRequest, JobStatus


class JobQueue:
    """Abstraction over Redis Streams for RLM job management."""

    def __init__(self, redis_client: aioredis.Redis, settings: Settings):
        self.redis = redis_client
        self.stream = settings.stream_name
        self.group = settings.consumer_group
        self.result_ttl = settings.job_result_ttl
        self.max_len = settings.job_max_len

    async def ensure_consumer_group(self) -> None:
        """Create the consumer group if it doesn't exist. MKSTREAM creates the stream."""
        try:
            await self.redis.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
        except Exception:
            pass  # Group already exists

    async def enqueue(self, request: CompletionRequest, api_key: str) -> str:
        """Add a job to the stream. Returns job_id."""
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Check idempotency
        if request.idempotency_key:
            existing = await self.redis.get(
                f"rlm:idempotency:{request.idempotency_key}"
            )
            if existing:
                return existing

        # Store job metadata hash
        job_key = f"rlm:job:{job_id}"
        request_json = request.model_dump_json()
        await self.redis.hset(
            job_key,
            mapping={
                "status": JobStatus.QUEUED.value,
                "created_at": now,
                "api_key": api_key,
                "request": request_json,
                "current_iteration": "0",
                "max_iterations": str(request.max_iterations),
            },
        )
        await self.redis.expire(job_key, self.result_ttl)

        # Add to stream
        msg_id = await self.redis.xadd(
            self.stream,
            {"job_id": job_id, "request": request_json, "created_at": now},
            maxlen=self.max_len,
            approximate=True,
        )

        # Store stream message ID for later ACK reference
        await self.redis.hset(job_key, "stream_message_id", msg_id)

        # Store idempotency mapping
        if request.idempotency_key:
            await self.redis.set(
                f"rlm:idempotency:{request.idempotency_key}",
                job_id,
                ex=self.result_ttl,
            )

        return job_id

    async def get_job_status(self, job_id: str) -> dict | None:
        """Get job metadata hash. Returns None if job not found."""
        data = await self.redis.hgetall(f"rlm:job:{job_id}")
        return data if data else None

    async def get_job_result(self, job_id: str) -> dict | None:
        """Get the completion result JSON."""
        raw = await self.redis.get(f"rlm:job:{job_id}:result")
        return json.loads(raw) if raw else None

    async def get_pending_count(self) -> int:
        """Get approximate number of pending messages in the stream."""
        try:
            info = await self.redis.xinfo_groups(self.stream)
            for group in info:
                if group["name"] == self.group:
                    return group.get("pending", 0) + group.get("lag", 0)
        except Exception:
            pass
        return 0
