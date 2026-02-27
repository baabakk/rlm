"""MongoDB client initialization — async (motor) for FastAPI, sync (pymongo) for worker."""

from __future__ import annotations

import logging

from api.config import Settings

logger = logging.getLogger("rlm-api")


# -- Async client (FastAPI) ---------------------------------------------------

_async_client = None
_async_db = None


async def init_mongo(settings: Settings):
    """Initialize async MongoDB client. Returns (client, database) or (None, None)."""
    global _async_client, _async_db
    if not settings.mongodb_uri:
        logger.info("MongoDB URI not configured, persistence disabled")
        return None, None

    from motor.motor_asyncio import AsyncIOMotorClient

    _async_client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    _async_db = _async_client[settings.mongodb_database]

    try:
        await _async_client.admin.command("ping")
        logger.info("MongoDB connected: %s", settings.mongodb_database)

        # Create indexes (idempotent — no-ops if they already exist)
        await _async_db.jobs.create_index("job_id", unique=True)
        await _async_db.jobs.create_index("created_at")
        await _async_db.jobs.create_index("status")
        await _async_db.jobs.create_index("api_key")
        await _async_db.jobs.create_index("backend")
        await _async_db.events.create_index([("job_id", 1), ("timestamp", 1)])
        await _async_db.events.create_index("event_type")
    except Exception as e:
        logger.warning("MongoDB connection failed, persistence disabled: %s", e)
        _async_client.close()
        _async_client = None
        _async_db = None
        return None, None

    return _async_client, _async_db


async def get_mongo_db():
    """FastAPI dependency — returns the async MongoDB database (or None)."""
    return _async_db


async def close_mongo():
    """Shutdown: close the async MongoDB client."""
    global _async_client, _async_db
    if _async_client:
        _async_client.close()
    _async_client = None
    _async_db = None


# -- Sync client (Worker) ----------------------------------------------------


def get_sync_mongo(settings: Settings):
    """Create a synchronous pymongo client for worker processes.

    Returns (client, db) or (None, None) if MongoDB is not configured.
    """
    if not settings.mongodb_uri:
        return None, None

    from pymongo import MongoClient

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[settings.mongodb_database]
    try:
        client.admin.command("ping")
    except Exception as e:
        logger.warning("MongoDB connection failed (worker), persistence disabled: %s", e)
        client.close()
        return None, None
    return client, db
