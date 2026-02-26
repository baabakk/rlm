"""Tests for api/worker.py — resolve_backend_kwargs."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic_settings")

from api.worker import resolve_backend_kwargs


class TestResolveBackendKwargs:
    """Tests for the backend kwargs resolution logic."""

    def test_basic_openai(self, mock_settings):
        request = {"backend": "openai", "model_name": "gpt-4", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["model_name"] == "gpt-4"
        assert result["api_key"] == "sk-test-openai"

    def test_safe_options_forwarded(self, mock_settings):
        request = {
            "backend": "openai",
            "model_name": "gpt-4",
            "backend_options": {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9},
        }
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 1000
        assert result["top_p"] == 0.9

    def test_unsafe_options_filtered(self, mock_settings):
        request = {
            "backend": "openai",
            "model_name": "gpt-4",
            "backend_options": {"base_url": "http://evil.com", "api_key": "stolen", "stream": True},
        }
        result = resolve_backend_kwargs(request, mock_settings)
        assert "base_url" not in result or result.get("base_url") != "http://evil.com"
        assert result["api_key"] == "sk-test-openai"
        assert "stream" not in result

    def test_anthropic_backend(self, mock_settings):
        request = {"backend": "anthropic", "model_name": "claude-3", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["api_key"] == "sk-test-anthropic"
        assert result["model_name"] == "claude-3"

    def test_azure_backend_includes_endpoint(self, mock_settings):
        request = {"backend": "azure_openai", "model_name": "gpt-4", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["api_key"] == "az-test"
        assert result["azure_endpoint"] == "https://test.openai.azure.com"
        assert result["api_version"] == "2024-02-15-preview"

    def test_vllm_backend_includes_base_url(self, mock_settings):
        request = {"backend": "vllm", "model_name": "local-model", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["base_url"] == "http://vllm:8000/v1"
        assert "api_key" not in result

    def test_empty_backend_options(self, mock_settings):
        request = {"backend": "openai", "model_name": "gpt-4", "backend_options": {}}
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["model_name"] == "gpt-4"
        assert result["api_key"] == "sk-test-openai"
        assert len(result) == 2

    def test_backend_with_no_configured_key(self, mock_settings):
        """Backends with empty API key should not include api_key in result."""
        request = {"backend": "gemini", "model_name": "gemini-pro", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert "api_key" not in result

    def test_openrouter_backend(self, mock_settings):
        request = {"backend": "openrouter", "model_name": "model-x", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert result["api_key"] == "or-test"

    def test_unknown_backend_no_key(self, mock_settings):
        """Unknown backends should not crash, just have no api_key."""
        request = {"backend": "unknown_provider", "model_name": "model-x", "backend_options": None}
        result = resolve_backend_kwargs(request, mock_settings)
        assert "api_key" not in result
        assert result["model_name"] == "model-x"
