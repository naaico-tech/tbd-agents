"""Redis-backed pub/sub event bus for SSE streaming.

Works across processes — Celery workers publish events via Redis,
FastAPI SSE endpoints subscribe via async Redis pub/sub.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "workflow:events:"
_pub_redis: aioredis.Redis | None = None


def _channel(workflow_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{workflow_id}"


async def publish(workflow_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Publish an event to a workflow's Redis channel.

    Uses a cached Redis connection; automatically reconnects if the
    connection is stale (e.g. new event loop in a Celery worker).
    """
    global _pub_redis
    payload = json.dumps(
        {"type": event_type, "data": data, "timestamp": datetime.now(UTC).isoformat()},
        default=str,
    )
    for attempt in range(2):
        try:
            if _pub_redis is None:
                _pub_redis = aioredis.from_url(
                    settings.redis_url, decode_responses=True
                )
            await _pub_redis.publish(_channel(workflow_id), payload)
            return
        except Exception:
            if _pub_redis is not None:
                try:
                    await _pub_redis.aclose()
                except Exception:
                    pass
                _pub_redis = None
    logger.warning("Failed to publish event for workflow %s", workflow_id)


async def subscribe(workflow_id: str) -> AsyncGenerator[str | None, None]:
    """Subscribe to a workflow's events via Redis pub/sub.

    Yields JSON payload strings, or None on timeout (for keepalive signalling).
    Automatically cleans up the subscription when the generator is closed.
    """
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(_channel(workflow_id))
    try:
        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=30.0
            )
            if msg is not None:
                yield msg["data"]
            else:
                yield None  # keepalive signal
    finally:
        await pubsub.unsubscribe(_channel(workflow_id))
        await pubsub.aclose()
        await r.aclose()

