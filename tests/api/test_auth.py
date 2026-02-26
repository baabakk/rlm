"""Tests for api/auth.py — verify_api_key."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import verify_api_key
from api.config import Settings


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class TestVerifyApiKeyEnvMode:
    """Tests for verify_api_key with api_key_source='env'."""

    async def test_valid_key_returns_token(self, mock_settings, mock_redis):
        result = await verify_api_key(_creds("test-key-1"), mock_settings, mock_redis)
        assert result == "test-key-1"

    async def test_second_valid_key(self, mock_settings, mock_redis):
        result = await verify_api_key(_creds("test-key-2"), mock_settings, mock_redis)
        assert result == "test-key-2"

    async def test_invalid_key_raises_401(self, mock_settings, mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(_creds("bad-key"), mock_settings, mock_redis)
        assert exc_info.value.status_code == 401

    async def test_no_keys_configured_raises_500(self, mock_redis):
        settings = Settings(
            _env_file=None,
            api_keys="",
            api_key_source="env",
            auth_disabled=False,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(_creds("anything"), settings, mock_redis)
        assert exc_info.value.status_code == 500

    async def test_whitespace_in_keys_handled(self, mock_redis):
        settings = Settings(
            _env_file=None,
            api_keys=" key-1 , key-2 ",
            api_key_source="env",
            auth_disabled=False,
        )
        result = await verify_api_key(_creds("key-1"), settings, mock_redis)
        assert result == "key-1"


class TestVerifyApiKeyRedisMode:
    """Tests for verify_api_key with api_key_source='redis'."""

    async def test_valid_key_in_redis_set(self, mock_redis):
        settings = Settings(
            _env_file=None,
            api_keys="",
            api_key_source="redis",
            auth_disabled=False,
        )
        mock_redis.sismember = AsyncMock(return_value=True)
        result = await verify_api_key(_creds("redis-key"), settings, mock_redis)
        assert result == "redis-key"
        mock_redis.sismember.assert_awaited_once_with("rlm:api_keys", "redis-key")

    async def test_invalid_key_not_in_redis(self, mock_redis):
        settings = Settings(
            _env_file=None,
            api_keys="",
            api_key_source="redis",
            auth_disabled=False,
        )
        mock_redis.sismember = AsyncMock(return_value=False)
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(_creds("bad-key"), settings, mock_redis)
        assert exc_info.value.status_code == 401


class TestVerifyApiKeyAuthDisabled:
    """Tests for verify_api_key with auth disabled."""

    async def test_any_token_accepted(self, mock_redis):
        settings = Settings(
            _env_file=None,
            api_keys="",
            api_key_source="env",
            auth_disabled=True,
        )
        result = await verify_api_key(_creds("literally-anything"), settings, mock_redis)
        assert result == "literally-anything"
