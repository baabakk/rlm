"""Tests for POST /v1/completions."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock

from api.config import Settings, get_settings
from api.redis_client import get_redis

AUTH_HEADER = {"Authorization": "Bearer test-key-1"}


class TestCreateCompletion:
    """Tests for the completions endpoint."""

    def test_success_returns_202(self, test_app):
        response = test_app.post(
            "/v1/completions",
            json={"prompt": "Hello, world!"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert "created_at" in data

    def test_missing_auth_returns_401_or_403(self, test_app):
        """Missing credentials returns 401 (no credentials) or 403 depending on version."""
        response = test_app.post("/v1/completions", json={"prompt": "test"})
        assert response.status_code in (401, 403)

    def test_invalid_auth_returns_401(self, test_app):
        response = test_app.post(
            "/v1/completions",
            json={"prompt": "test"},
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert response.status_code == 401

    def test_empty_prompt_returns_422(self, test_app):
        response = test_app.post(
            "/v1/completions",
            json={"prompt": ""},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 422

    def test_oversized_prompt_returns_413(self, test_app, mock_settings, mock_redis):
        """A prompt exceeding the configurable max_prompt_length returns 413."""
        # Override settings with a very small prompt limit
        small_limit_settings = Settings(
            _env_file=None,
            api_keys="test-key-1",
            api_key_source="env",
            auth_disabled=False,
            rate_limit_enabled=False,
            max_prompt_length=100,
        )
        app = test_app.app
        app.dependency_overrides[get_settings] = lambda: small_limit_settings
        app.dependency_overrides[get_redis] = lambda: mock_redis

        response = test_app.post(
            "/v1/completions",
            json={"prompt": "x" * 200},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 413

    def test_rate_limited_returns_429(self, test_app, mock_redis):
        mock_redis.eval = AsyncMock(return_value=0)
        response = test_app.post(
            "/v1/completions",
            json={"prompt": "test"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 429

    def test_with_backend_options(self, test_app):
        response = test_app.post(
            "/v1/completions",
            json={
                "prompt": "test",
                "backend": "openai",
                "model_name": "gpt-4",
                "backend_options": {"temperature": 0.5},
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 202

    def test_with_idempotency_key(self, test_app):
        response = test_app.post(
            "/v1/completions",
            json={"prompt": "test", "idempotency_key": "idem-1"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 202
