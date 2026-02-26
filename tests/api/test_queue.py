"""Tests for api/queue.py — JobQueue."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock

from api.models import CompletionRequest
from api.queue import JobQueue


class TestJobQueueEnqueue:
    """Tests for JobQueue.enqueue."""

    async def test_returns_uuid_string(self, mock_settings, mock_redis):
        queue = JobQueue(mock_redis, mock_settings)
        request = CompletionRequest(prompt="test prompt")
        job_id = await queue.enqueue(request, "test-key")
        assert isinstance(job_id, str)
        assert len(job_id) == 36  # UUID format

    async def test_creates_hash_and_stream_entry(self, mock_settings, mock_redis):
        queue = JobQueue(mock_redis, mock_settings)
        request = CompletionRequest(prompt="test")
        job_id = await queue.enqueue(request, "test-key")

        # Verify hash was created
        mock_redis.hset.assert_awaited()
        hset_call = mock_redis.hset.call_args_list[0]
        assert hset_call[0][0] == f"rlm:job:{job_id}"
        mapping = hset_call[1]["mapping"]
        assert mapping["status"] == "queued"
        assert mapping["api_key"] == "test-key"

        # Verify stream entry was added
        mock_redis.xadd.assert_awaited_once()

    async def test_idempotency_returns_existing_job(self, mock_settings, mock_redis):
        mock_redis.set = AsyncMock(return_value=False)  # NX failed
        mock_redis.get = AsyncMock(return_value="existing-job-id")

        queue = JobQueue(mock_redis, mock_settings)
        request = CompletionRequest(prompt="test", idempotency_key="idem-123")
        job_id = await queue.enqueue(request, "test-key")

        assert job_id == "existing-job-id"
        mock_redis.xadd.assert_not_awaited()

    async def test_idempotency_new_job(self, mock_settings, mock_redis):
        mock_redis.set = AsyncMock(return_value=True)  # NX succeeded

        queue = JobQueue(mock_redis, mock_settings)
        request = CompletionRequest(prompt="test", idempotency_key="new-idem")
        job_id = await queue.enqueue(request, "test-key")

        assert isinstance(job_id, str)
        assert len(job_id) == 36
        mock_redis.xadd.assert_awaited_once()


class TestJobQueueGetJobStatus:
    """Tests for JobQueue.get_job_status."""

    async def test_returns_data_when_found(self, mock_settings, mock_redis):
        mock_redis.hgetall = AsyncMock(
            return_value={
                "status": "processing",
                "created_at": "2025-01-01T00:00:00",
                "api_key": "test-key",
            }
        )
        queue = JobQueue(mock_redis, mock_settings)
        result = await queue.get_job_status("some-job-id")
        assert result is not None
        assert result["status"] == "processing"

    async def test_returns_none_when_not_found(self, mock_settings, mock_redis):
        mock_redis.hgetall = AsyncMock(return_value={})
        queue = JobQueue(mock_redis, mock_settings)
        result = await queue.get_job_status("nonexistent")
        assert result is None


class TestJobQueueGetJobResult:
    """Tests for JobQueue.get_job_result."""

    async def test_returns_parsed_json(self, mock_settings, mock_redis):
        mock_redis.get = AsyncMock(return_value=json.dumps({"response": "hello"}))
        queue = JobQueue(mock_redis, mock_settings)
        result = await queue.get_job_result("job-123")
        assert result == {"response": "hello"}

    async def test_returns_none_when_no_result(self, mock_settings, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        queue = JobQueue(mock_redis, mock_settings)
        result = await queue.get_job_result("job-123")
        assert result is None


class TestJobQueueEnsureConsumerGroup:
    """Tests for JobQueue.ensure_consumer_group."""

    async def test_creates_group(self, mock_settings, mock_redis):
        queue = JobQueue(mock_redis, mock_settings)
        await queue.ensure_consumer_group()
        mock_redis.xgroup_create.assert_awaited_once_with(
            "rlm:jobs", "rlm-workers", id="0", mkstream=True
        )

    async def test_ignores_existing_group(self, mock_settings, mock_redis):
        mock_redis.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        queue = JobQueue(mock_redis, mock_settings)
        await queue.ensure_consumer_group()  # Should not raise
