"""Tests for api/persistence.py — AsyncJobStore and SyncJobStore."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic_settings")

from unittest.mock import AsyncMock, MagicMock

from api.persistence import AsyncJobStore, SyncJobStore


class TestAsyncJobStore:
    """Tests for the async job store (motor, FastAPI side)."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.jobs = AsyncMock()
        db.jobs.insert_one = AsyncMock()
        db.events = AsyncMock()
        db.events.insert_one = AsyncMock()
        return db

    async def test_create_job_inserts_document(self, mock_db):
        store = AsyncJobStore(mock_db)
        request = MagicMock()
        request.model_dump.return_value = {
            "prompt": "hello",
            "backend": "openai",
            "model_name": "gpt-4.1",
        }
        await store.create_job("job-123", request, "test-key")

        mock_db.jobs.insert_one.assert_called_once()
        doc = mock_db.jobs.insert_one.call_args[0][0]
        assert doc["job_id"] == "job-123"
        assert doc["status"] == "queued"
        assert doc["api_key"] == "test-key"
        assert doc["backend"] == "openai"
        assert doc["model_name"] == "gpt-4.1"
        assert doc["prompt"] == "hello"
        assert doc["iterations"] == []
        assert doc["result"] is None

    async def test_create_job_handles_dict_request(self, mock_db):
        store = AsyncJobStore(mock_db)
        request = {"prompt": "hello", "backend": "openai", "model_name": "gpt-4.1"}
        await store.create_job("job-456", request, "test-key")

        mock_db.jobs.insert_one.assert_called_once()
        doc = mock_db.jobs.insert_one.call_args[0][0]
        assert doc["job_id"] == "job-456"

    async def test_create_job_failsafe_on_error(self, mock_db):
        mock_db.jobs.insert_one = AsyncMock(side_effect=Exception("Connection lost"))
        store = AsyncJobStore(mock_db)
        request = {"prompt": "hello"}
        # Should not raise
        await store.create_job("job-err", request, "key")

    async def test_create_job_noop_when_db_is_none(self):
        store = AsyncJobStore(None)
        # Should not raise
        await store.create_job("job-none", {"prompt": "hi"}, "key")


class TestSyncJobStore:
    """Tests for the sync job store (pymongo, worker side)."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.jobs = MagicMock()
        db.jobs.update_one = MagicMock()
        db.events = MagicMock()
        db.events.insert_one = MagicMock()
        return db

    def test_mark_processing(self, mock_db):
        store = SyncJobStore(mock_db)
        store.mark_processing("job-1", "worker-abc")

        mock_db.jobs.update_one.assert_called_once()
        args = mock_db.jobs.update_one.call_args
        assert args[0][0] == {"job_id": "job-1"}
        update = args[0][1]["$set"]
        assert update["status"] == "processing"
        assert update["worker_id"] == "worker-abc"
        assert "started_at" in update

    def test_log_event_inserts_event(self, mock_db):
        store = SyncJobStore(mock_db)
        store.log_event("job-1", "started", {"worker_id": "w1"})

        mock_db.events.insert_one.assert_called_once()
        doc = mock_db.events.insert_one.call_args[0][0]
        assert doc["job_id"] == "job-1"
        assert doc["event_type"] == "started"
        assert doc["data"] == {"worker_id": "w1"}

    def test_log_event_pushes_iteration(self, mock_db):
        store = SyncJobStore(mock_db)
        iter_data = {"iteration": 1, "code": "print(1)", "result": "1"}
        store.log_event("job-1", "iteration", iter_data)

        # Should insert event AND push iteration to job doc
        mock_db.events.insert_one.assert_called_once()
        mock_db.jobs.update_one.assert_called_once()
        push_args = mock_db.jobs.update_one.call_args
        assert push_args[0][0] == {"job_id": "job-1"}
        assert push_args[0][1]["$push"]["iterations"] == iter_data

    def test_log_event_non_iteration_does_not_push(self, mock_db):
        store = SyncJobStore(mock_db)
        store.log_event("job-1", "metadata", {"model": "gpt-4.1"})

        mock_db.events.insert_one.assert_called_once()
        mock_db.jobs.update_one.assert_not_called()

    def test_mark_completed(self, mock_db):
        store = SyncJobStore(mock_db)
        result = {"execution_time": 4.2, "usage_summary": {"total": 100}, "response": "answer"}
        store.mark_completed("job-1", result)

        args = mock_db.jobs.update_one.call_args
        update = args[0][1]["$set"]
        assert update["status"] == "completed"
        assert update["result"] == result
        assert update["execution_time"] == 4.2
        assert update["usage_summary"] == {"total": 100}

    def test_mark_failed(self, mock_db):
        store = SyncJobStore(mock_db)
        store.mark_failed("job-1", "Something went wrong")

        args = mock_db.jobs.update_one.call_args
        update = args[0][1]["$set"]
        assert update["status"] == "failed"
        assert update["error"] == "Something went wrong"

    def test_all_methods_failsafe(self, mock_db):
        mock_db.jobs.update_one = MagicMock(side_effect=Exception("DB down"))
        mock_db.events.insert_one = MagicMock(side_effect=Exception("DB down"))
        store = SyncJobStore(mock_db)

        # None of these should raise
        store.mark_processing("j", "w")
        store.log_event("j", "iteration", {"iteration": 1})
        store.mark_completed("j", {"execution_time": 1.0})
        store.mark_failed("j", "error")

    def test_noop_when_db_is_none(self):
        store = SyncJobStore(None)
        # None of these should raise
        store.mark_processing("j", "w")
        store.log_event("j", "started", {})
        store.mark_completed("j", {})
        store.mark_failed("j", "err")
