"""Tests for GET /health."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_healthy_with_redis(self, test_app, mock_redis):
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.zcount = AsyncMock(return_value=4)
        response = test_app.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["redis_connected"] is True
        assert data["active_workers"] == 4
        assert "version" in data

    def test_degraded_when_redis_down(self, test_app, mock_redis):
        mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))
        mock_redis.zcount = AsyncMock(side_effect=Exception("Connection refused"))
        mock_redis.xinfo_groups = AsyncMock(side_effect=Exception("Connection refused"))
        response = test_app.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["redis_connected"] is False

    def test_no_auth_required(self, test_app):
        """Health endpoint works without Authorization header."""
        response = test_app.get("/health")
        assert response.status_code == 200
