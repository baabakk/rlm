"""Tests for api/rate_limit.py — check_rate_limit."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock

from fastapi import HTTPException

from api.config import Settings
from api.rate_limit import check_rate_limit


class TestCheckRateLimit:
    """Tests for the sliding-window rate limiter."""

    async def test_allowed_when_under_limit(self, mock_settings, mock_redis):
        mock_redis.eval = AsyncMock(return_value=1)
        await check_rate_limit("test-key", mock_redis, mock_settings)
        mock_redis.eval.assert_awaited_once()

    async def test_raises_429_when_limit_exceeded(self, mock_settings, mock_redis):
        mock_redis.eval = AsyncMock(return_value=0)
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit("test-key", mock_redis, mock_settings)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert "X-RateLimit-Limit" in exc_info.value.headers
        assert "X-RateLimit-Remaining" in exc_info.value.headers

    async def test_skipped_when_disabled(self, mock_redis):
        settings = Settings(
            _env_file=None,
            rate_limit_enabled=False,
        )
        await check_rate_limit("test-key", mock_redis, settings)
        mock_redis.eval.assert_not_awaited()

    async def test_lua_script_receives_correct_key(self, mock_settings, mock_redis):
        mock_redis.eval = AsyncMock(return_value=1)
        await check_rate_limit("my-api-key", mock_redis, mock_settings)
        call_args = mock_redis.eval.call_args
        # KEYS[1] is the rate limit key
        assert call_args[0][2] == "rlm:ratelimit:my-api-key"
