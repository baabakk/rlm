"""Shared fixtures for API tests."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import Settings, get_settings
from api.queue import JobQueue
from api.redis_client import get_redis
from api.routes import completions_router, health_router, jobs_router


@pytest.fixture
def mock_settings():
    """Settings instance with known test values. No .env file loading."""
    return Settings(
        _env_file=None,
        api_keys="test-key-1,test-key-2",
        api_key_source="env",
        auth_disabled=False,
        rate_limit_enabled=True,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        redis_url="redis://localhost:6379/0",
        redis_password="",
        redis_max_connections=5,
        stream_name="rlm:jobs",
        consumer_group="rlm-workers",
        consumer_prefix="worker",
        stream_block_ms=5000,
        job_result_ttl=3600,
        job_max_len=100000,
        worker_batch_size=1,
        job_timeout_seconds=600,
        max_prompt_length=1_000_000,
        cors_origins="*",
        default_backend="openai",
        default_model="gpt-test",
        default_max_depth=1,
        default_max_iterations=30,
        openai_api_key="sk-test-openai",
        anthropic_api_key="sk-test-anthropic",
        gemini_api_key="",
        azure_openai_api_key="az-test",
        azure_openai_endpoint="https://test.openai.azure.com",
        azure_openai_api_version="2024-02-15-preview",
        portkey_api_key="",
        openrouter_api_key="or-test",
        vercel_api_key="",
        litellm_api_key="",
        vllm_base_url="http://vllm:8000/v1",
    )


@pytest.fixture
def mock_redis():
    """AsyncMock Redis client with sensible defaults."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.sismember = AsyncMock(return_value=True)
    redis.eval = AsyncMock(return_value=1)
    redis.hset = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.xadd = AsyncMock(return_value="1234567890-0")
    redis.xgroup_create = AsyncMock()
    redis.xinfo_groups = AsyncMock(return_value=[])
    redis.zcount = AsyncMock(return_value=0)
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
def test_app(mock_settings, mock_redis):
    """FastAPI TestClient with mocked dependencies (no lifespan)."""
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(completions_router)
    app.include_router(jobs_router)

    queue = JobQueue(mock_redis, mock_settings)
    app.state.redis = mock_redis
    app.state.queue = queue
    app.state.settings = mock_settings

    app.dependency_overrides[get_settings] = lambda: mock_settings
    app.dependency_overrides[get_redis] = lambda: mock_redis

    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()
