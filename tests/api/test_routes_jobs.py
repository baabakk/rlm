"""Tests for GET /v1/jobs/{job_id}."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock

AUTH_HEADER = {"Authorization": "Bearer test-key-1"}


class TestGetJob:
    """Tests for the job polling endpoint."""

    def test_queued_job(self, test_app, mock_redis):
        mock_redis.hgetall = AsyncMock(
            return_value={
                "status": "queued",
                "created_at": "2025-01-01T00:00:00",
                "api_key": "test-key-1",
                "current_iteration": "0",
                "max_iterations": "30",
            }
        )
        response = test_app.get("/v1/jobs/some-job-id", headers=AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["job_id"] == "some-job-id"

    def test_not_found_returns_404(self, test_app, mock_redis):
        mock_redis.hgetall = AsyncMock(return_value={})
        response = test_app.get("/v1/jobs/nonexistent", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_wrong_owner_returns_404(self, test_app, mock_redis):
        mock_redis.hgetall = AsyncMock(
            return_value={
                "status": "queued",
                "created_at": "2025-01-01T00:00:00",
                "api_key": "different-key",
                "current_iteration": "0",
                "max_iterations": "30",
            }
        )
        response = test_app.get("/v1/jobs/some-job-id", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_completed_job_includes_result(self, test_app, mock_redis):
        mock_redis.hgetall = AsyncMock(
            return_value={
                "status": "completed",
                "created_at": "2025-01-01T00:00:00",
                "started_at": "2025-01-01T00:00:01",
                "completed_at": "2025-01-01T00:00:05",
                "api_key": "test-key-1",
                "current_iteration": "12",
                "max_iterations": "30",
            }
        )
        mock_redis.get = AsyncMock(
            return_value=json.dumps(
                {
                    "root_model": "gpt-4",
                    "prompt": "test",
                    "response": "answer",
                    "usage_summary": {
                        "model_usage_summaries": {
                            "gpt-4": {
                                "total_calls": 12,
                                "total_input_tokens": 8000,
                                "total_output_tokens": 3000,
                            }
                        }
                    },
                    "execution_time": 4.21,
                }
            )
        )
        response = test_app.get("/v1/jobs/some-job-id", headers=AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"]["response"] == "answer"
        assert data["current_iteration"] == 12

    def test_failed_job_includes_error(self, test_app, mock_redis):
        mock_redis.hgetall = AsyncMock(
            return_value={
                "status": "failed",
                "created_at": "2025-01-01T00:00:00",
                "api_key": "test-key-1",
                "error": "Something went wrong",
                "current_iteration": "5",
                "max_iterations": "30",
            }
        )
        response = test_app.get("/v1/jobs/some-job-id", headers=AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Something went wrong"
