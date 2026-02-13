from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration loaded from environment variables with RLM_ prefix."""

    # --- API Server ---
    api_host: str = "0.0.0.0"
    api_port: int = 26030
    api_workers: int = 4
    api_log_level: str = "info"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""
    redis_max_connections: int = 20

    # --- Job Queue (Redis Streams) ---
    stream_name: str = "rlm:jobs"
    consumer_group: str = "rlm-workers"
    consumer_prefix: str = "worker"
    stream_block_ms: int = 5000
    job_result_ttl: int = 3600  # 1 hour
    job_max_len: int = 100000

    # --- Worker ---
    worker_batch_size: int = 1

    # --- Auth ---
    api_keys: str = ""  # comma-separated valid API keys
    api_key_source: Literal["env", "redis"] = "env"

    # --- Rate Limiting ---
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # --- RLM Defaults ---
    default_backend: str = "openai"
    default_model: str = "gpt-5-nano"
    default_max_depth: int = 1
    default_max_iterations: int = 30

    # --- Backend API Keys ---
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-15-preview"
    portkey_api_key: str = ""
    openrouter_api_key: str = ""
    vercel_api_key: str = ""
    litellm_api_key: str = ""
    vllm_base_url: str = ""

    model_config = {"env_prefix": "RLM_", "env_file": ".env", "extra": "ignore"}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
