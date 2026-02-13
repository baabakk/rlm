from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# -- Request Models -----------------------------------------------------------


class CompletionRequest(BaseModel):
    """POST /v1/completions request body."""

    prompt: str | dict[str, Any] | list[dict[str, Any]]
    backend: Literal[
        "openai",
        "anthropic",
        "gemini",
        "azure_openai",
        "portkey",
        "openrouter",
        "vercel",
        "vllm",
        "litellm",
    ] = "openai"
    model_name: str = "gpt-5-nano"
    max_depth: int = Field(default=1, ge=0, le=3)
    max_iterations: int = Field(default=30, ge=1, le=100)
    root_prompt: str | None = None
    idempotency_key: str | None = None
    backend_options: dict[str, Any] | None = None

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str | dict | list) -> str | dict | list:
        if isinstance(v, str) and len(v.strip()) == 0:
            raise ValueError("prompt must not be empty")
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("prompt messages list must not be empty")
        return v


# -- Job Status ---------------------------------------------------------------


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# -- Response Models ----------------------------------------------------------


class CompletionResponse(BaseModel):
    """Response from POST /v1/completions — job accepted."""

    job_id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime
    message: str = "Job enqueued successfully"


class ModelUsageResponse(BaseModel):
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int


class UsageSummaryResponse(BaseModel):
    model_usage_summaries: dict[str, ModelUsageResponse]


class CompletionResultResponse(BaseModel):
    """Mirrors RLMChatCompletion.to_dict() shape."""

    root_model: str
    prompt: str | dict[str, Any] | list[dict[str, Any]]
    response: str
    usage_summary: UsageSummaryResponse
    execution_time: float


class JobResultResponse(BaseModel):
    """Response from GET /v1/jobs/{job_id}."""

    job_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: CompletionResultResponse | None = None
    error: str | None = None
    current_iteration: int = 0
    max_iterations: int = 30


# -- SSE Events ---------------------------------------------------------------


class SSEEvent(BaseModel):
    """Published per RLM event for SSE streaming."""

    job_id: str
    event_type: Literal["started", "metadata", "iteration", "completed", "failed"]
    data: dict[str, Any] | None = None
    timestamp: datetime


# -- Health -------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    redis_connected: bool
    active_workers: int
    pending_jobs: int


# -- Error --------------------------------------------------------------------


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int
