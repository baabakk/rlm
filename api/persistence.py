"""MongoDB persistence layer for RLM job data.

Two store classes:
- AsyncJobStore: used by FastAPI routes (motor, async)
- SyncJobStore: used by worker processes (pymongo, sync)

All writes are fail-safe — exceptions are logged but never raised,
so MongoDB outages never block the Redis hot path.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger("rlm-api")


class AsyncJobStore:
    """Async persistence for FastAPI routes (motor)."""

    def __init__(self, db):
        self.db = db

    async def create_job(self, job_id: str, request, api_key: str) -> None:
        """Insert initial job document at enqueue time."""
        if self.db is None:
            return
        try:
            request_dict = request.model_dump() if hasattr(request, "model_dump") else request
            doc = {
                "job_id": job_id,
                "status": "queued",
                "api_key": api_key,
                "backend": request_dict.get("backend"),
                "model_name": request_dict.get("model_name"),
                "prompt": request_dict.get("prompt"),
                "request": request_dict,
                "created_at": datetime.now(UTC).isoformat(),
                "started_at": None,
                "completed_at": None,
                "worker_id": None,
                "iterations": [],
                "result": None,
                "error": None,
                "execution_time": None,
                "usage_summary": None,
            }
            await self.db.jobs.insert_one(doc)
        except Exception as e:
            logger.warning("MongoDB: failed to create job %s: %s", job_id, e)


class SyncJobStore:
    """Sync persistence for worker processes (pymongo)."""

    def __init__(self, db):
        self.db = db

    def mark_processing(self, job_id: str, worker_id: str) -> None:
        """Update job status to processing."""
        if self.db is None:
            return
        try:
            self.db.jobs.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "processing",
                        "started_at": datetime.now(UTC).isoformat(),
                        "worker_id": worker_id,
                    }
                },
            )
        except Exception as e:
            logger.warning("MongoDB: failed to mark_processing %s: %s", job_id, e)

    def log_event(self, job_id: str, event_type: str, data: dict) -> None:
        """Append event to the events collection and push iterations to the job doc."""
        if self.db is None:
            return
        try:
            event_doc = {
                "job_id": job_id,
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self.db.events.insert_one(event_doc)

            # Also push iteration data into the job's embedded array
            if event_type == "iteration":
                self.db.jobs.update_one(
                    {"job_id": job_id},
                    {"$push": {"iterations": data}},
                )
        except Exception as e:
            logger.warning("MongoDB: failed to log_event %s/%s: %s", job_id, event_type, e)

    def mark_completed(self, job_id: str, result_dict: dict) -> None:
        """Update job status to completed with full result."""
        if self.db is None:
            return
        try:
            self.db.jobs.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(UTC).isoformat(),
                        "result": result_dict,
                        "execution_time": result_dict.get("execution_time"),
                        "usage_summary": result_dict.get("usage_summary"),
                    }
                },
            )
        except Exception as e:
            logger.warning("MongoDB: failed to mark_completed %s: %s", job_id, e)

    def mark_failed(self, job_id: str, error: str) -> None:
        """Update job status to failed with error message."""
        if self.db is None:
            return
        try:
            self.db.jobs.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.now(UTC).isoformat(),
                        "error": error,
                    }
                },
            )
        except Exception as e:
            logger.warning("MongoDB: failed to mark_failed %s: %s", job_id, e)
