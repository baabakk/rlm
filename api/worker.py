"""
RLM Worker Process

Consumes jobs from Redis Streams, runs RLM.completion(), publishes events.
Each worker process handles one job at a time (RLM is not thread-safe).

Entry point: python -m api.worker
"""

from __future__ import annotations

import json
import logging
import os
import platform
import signal
import socket
import threading
import time
from datetime import UTC, datetime

import redis as sync_redis

from api.config import Settings, get_settings
from api.redis_client import get_sync_redis
from rlm import RLM
from rlm.core.types import RLMIteration, RLMMetadata

logger = logging.getLogger("rlm-worker")


# -- Graceful Shutdown --------------------------------------------------------

_shutdown = threading.Event()


def _handle_signal(signum: int, _frame) -> None:
    logger.info("Received signal %s, initiating graceful shutdown...", signum)
    _shutdown.set()


class JobTimeoutError(Exception):
    pass


def _handle_alarm(signum: int, _frame) -> None:
    raise JobTimeoutError("Job exceeded timeout limit")


# -- Streaming Callback Logger ------------------------------------------------


class StreamingCallbackLogger:
    """
    Implements the same interface as RLMLogger but publishes iteration data
    to Redis Pub/Sub for real-time SSE streaming.

    RLM calls:
        self.logger.log_metadata(metadata)   # once at init
        self.logger.log(iteration)           # per iteration
    """

    def __init__(
        self,
        redis_client: sync_redis.Redis,
        job_id: str,
        job_key: str,
    ):
        self.redis = redis_client
        self.job_id = job_id
        self.job_key = job_key
        self._iteration_count = 0

    def log_metadata(self, metadata: RLMMetadata) -> None:
        self._publish("metadata", metadata.to_dict())

    def log(self, iteration: RLMIteration) -> None:
        self._iteration_count += 1
        self.redis.hset(self.job_key, "current_iteration", str(self._iteration_count))
        self._publish(
            "iteration",
            {
                "iteration": self._iteration_count,
                **iteration.to_dict(),
            },
        )

    @property
    def iteration_count(self) -> int:
        return self._iteration_count

    def _publish(self, event_type: str, data: dict) -> None:
        event = json.dumps(
            {
                "job_id": self.job_id,
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        try:
            self.redis.publish(f"rlm:job:{self.job_id}:events", event)
        except Exception as e:
            logger.warning("Failed to publish event for job %s: %s", self.job_id, e)


# -- Backend Key Resolution ---------------------------------------------------

# Safe backend_options keys that users may pass per-request
_SAFE_BACKEND_OPTIONS = {"max_tokens", "temperature", "top_p"}


def resolve_backend_kwargs(request: dict, settings: Settings) -> dict:
    """
    Build backend_kwargs from the request + server-side env vars.
    Users specify backend + model_name. API keys come from env vars only.
    """
    kwargs: dict = {"model_name": request["model_name"]}

    # Merge whitelisted user options
    if request.get("backend_options"):
        for k, v in request["backend_options"].items():
            if k in _SAFE_BACKEND_OPTIONS:
                kwargs[k] = v

    # Resolve API key from env
    backend = request["backend"]
    key_map = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
        "azure_openai": settings.azure_openai_api_key,
        "portkey": settings.portkey_api_key,
        "openrouter": settings.openrouter_api_key,
        "vercel": settings.vercel_api_key,
        "litellm": settings.litellm_api_key,
        "cerebras": settings.cerebras_api_key,
        "vllm": "",
    }

    api_key = key_map.get(backend, "")
    if api_key:
        kwargs["api_key"] = api_key

    # Backend-specific extras
    if backend == "azure_openai":
        kwargs["azure_endpoint"] = settings.azure_openai_endpoint
        kwargs["api_version"] = settings.azure_openai_api_version
    elif backend == "vllm":
        kwargs["base_url"] = settings.vllm_base_url

    return kwargs


# -- Heartbeat ----------------------------------------------------------------


def _heartbeat_loop(
    redis_client: sync_redis.Redis,
    consumer_name: str,
) -> None:
    """Background thread that updates worker heartbeat and prunes stale entries."""
    cleanup_counter = 0
    while not _shutdown.is_set():
        try:
            now = time.time()
            redis_client.zadd("rlm:workers:heartbeat", {consumer_name: now})
            cleanup_counter += 1
            if cleanup_counter >= 6:  # Every ~60s
                redis_client.zremrangebyscore("rlm:workers:heartbeat", "-inf", now - 60)
                cleanup_counter = 0
        except Exception:
            pass
        _shutdown.wait(10)


# -- Job Processing -----------------------------------------------------------


def _process_job(
    redis_client: sync_redis.Redis,
    job_id: str,
    request_json: str,
    msg_id: str,
    consumer_name: str,
    settings: Settings,
) -> None:
    """Process a single RLM completion job."""
    request = json.loads(request_json)
    job_key = f"rlm:job:{job_id}"
    now_iso = datetime.now(UTC).isoformat()

    # Resolve None defaults from settings
    if request.get("backend") is None:
        request["backend"] = settings.default_backend
    if request.get("model_name") is None:
        request["model_name"] = settings.default_model
    if request.get("max_depth") is None:
        request["max_depth"] = settings.default_max_depth
    if request.get("max_iterations") is None:
        request["max_iterations"] = settings.default_max_iterations

    # Mark as processing
    redis_client.hset(
        job_key,
        mapping={
            "status": "processing",
            "started_at": now_iso,
            "worker_id": consumer_name,
        },
    )

    callback_logger = StreamingCallbackLogger(redis_client, job_id, job_key)
    callback_logger._publish("started", {"worker_id": consumer_name})

    # Set job timeout (Unix only)
    use_alarm = platform.system() != "Windows"
    old_alarm_handler = None
    try:
        if use_alarm:
            old_alarm_handler = signal.signal(signal.SIGALRM, _handle_alarm)
            signal.alarm(settings.job_timeout_seconds)

        backend_kwargs = resolve_backend_kwargs(request, settings)

        rlm_instance = RLM(
            backend=request["backend"],
            backend_kwargs=backend_kwargs,
            environment="local",
            max_depth=request["max_depth"],
            max_iterations=request["max_iterations"],
            logger=callback_logger,
            verbose=False,
        )

        result = rlm_instance.completion(
            prompt=request["prompt"],
            root_prompt=request.get("root_prompt"),
        )

        if use_alarm:
            signal.alarm(0)

        # Store result
        result_dict = result.to_dict()
        redis_client.set(
            f"rlm:job:{job_id}:result",
            json.dumps(result_dict),
            ex=settings.job_result_ttl,
        )
        redis_client.hset(
            job_key,
            mapping={
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )
        redis_client.expire(job_key, settings.job_result_ttl)

        callback_logger._publish("completed", result_dict)
        logger.info("Job %s completed in %.2fs", job_id, result.execution_time)

    except JobTimeoutError:
        logger.error("Job %s timed out after %ds", job_id, settings.job_timeout_seconds)
        redis_client.hset(
            job_key,
            mapping={
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "error": f"Job timed out after {settings.job_timeout_seconds} seconds",
            },
        )
        redis_client.expire(job_key, settings.job_result_ttl)
        callback_logger._publish("failed", {"error": "Job timed out"})

    except Exception as e:
        logger.error("Job %s failed: %s", job_id, e, exc_info=True)
        redis_client.hset(
            job_key,
            mapping={
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "error": str(e),
            },
        )
        redis_client.expire(job_key, settings.job_result_ttl)
        callback_logger._publish("failed", {"error": str(e)})

    finally:
        if use_alarm:
            signal.alarm(0)
            if old_alarm_handler is not None:
                signal.signal(signal.SIGALRM, old_alarm_handler)
        redis_client.xack(settings.stream_name, settings.consumer_group, msg_id)


# -- Stale Job Recovery -------------------------------------------------------


def _claim_stale_messages(
    redis_client: sync_redis.Redis,
    consumer_name: str,
    settings: Settings,
    min_idle_ms: int = 60_000,
) -> list[tuple[str, dict]]:
    """Claim messages pending for > min_idle_ms. Returns claimed entries."""
    result = redis_client.xautoclaim(
        name=settings.stream_name,
        groupname=settings.consumer_group,
        consumername=consumer_name,
        min_idle_time=min_idle_ms,
        start_id="0-0",
        count=10,
    )
    claimed: list[tuple[str, dict]] = []
    if result and len(result) >= 2:
        for msg_id, fields in result[1]:
            if fields:
                job_id = fields.get("job_id", "unknown")
                logger.info("Reclaimed stale job %s (msg_id=%s)", job_id, msg_id)
                job_key = f"rlm:job:{job_id}"
                redis_client.hset(job_key, "status", "queued")
                claimed.append((msg_id, fields))
    return claimed


# -- Main Worker Loop ---------------------------------------------------------


def run_worker() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    settings = get_settings()
    consumer_name = f"{settings.consumer_prefix}-{socket.gethostname()}-{os.getpid()}"

    logger.info("Starting worker: %s", consumer_name)

    redis_client = get_sync_redis(settings)

    # Ensure consumer group exists
    try:
        redis_client.xgroup_create(
            settings.stream_name, settings.consumer_group, id="0", mkstream=True
        )
    except Exception:
        pass

    # Start heartbeat thread
    hb = threading.Thread(target=_heartbeat_loop, args=(redis_client, consumer_name), daemon=True)
    hb.start()

    logger.info("Worker %s listening on stream '%s'", consumer_name, settings.stream_name)
    logger.warning(
        "Worker uses 'local' environment (unsandboxed exec). "
        "Do not process untrusted prompts without switching to a sandboxed environment."
    )

    # Recover stale jobs from crashed workers
    claimed: list[tuple[str, dict]] = []
    try:
        claimed = _claim_stale_messages(redis_client, consumer_name, settings)
    except Exception as e:
        logger.warning("Failed to claim stale messages: %s", e)

    for msg_id, fields in claimed:
        if _shutdown.is_set():
            break
        job_id = fields.get("job_id", "unknown")
        logger.info("Processing reclaimed job %s", job_id)
        _process_job(
            redis_client,
            job_id,
            fields["request"],
            msg_id,
            consumer_name,
            settings,
        )

    # Main consume loop
    while not _shutdown.is_set():
        try:
            messages = redis_client.xreadgroup(
                groupname=settings.consumer_group,
                consumername=consumer_name,
                streams={settings.stream_name: ">"},
                count=settings.worker_batch_size,
                block=settings.stream_block_ms,
            )

            if not messages:
                continue

            for _stream_name, entries in messages:
                for msg_id, fields in entries:
                    if _shutdown.is_set():
                        logger.info("Shutdown requested, skipping new job")
                        break

                    job_id = fields.get("job_id", "unknown")
                    logger.info("Processing job %s (msg_id=%s)", job_id, msg_id)
                    _process_job(
                        redis_client,
                        job_id,
                        fields["request"],
                        msg_id,
                        consumer_name,
                        settings,
                    )

        except Exception as e:
            logger.error("Worker loop error: %s", e, exc_info=True)
            time.sleep(1)

    # Cleanup
    logger.info("Worker %s shutting down", consumer_name)
    redis_client.zrem("rlm:workers:heartbeat", consumer_name)
    redis_client.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    run_worker()
