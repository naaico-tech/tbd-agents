"""Redis-backed pub/sub event bus for SSE streaming.

Works across processes — Celery workers publish events via Redis,
FastAPI SSE endpoints subscribe via async Redis pub/sub.

Supports SSE reconnection via ``Last-Event-ID``: each published event
is assigned a monotonic ID and stored in a short-lived Redis list so
that reconnecting clients can replay missed events.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "workflow:events:"
_HISTORY_PREFIX = "workflow:history:"
_COUNTER_PREFIX = "workflow:eventid:"
_TASK_STATUS_STREAM = "task:status:events"
_HISTORY_TTL = 300  # seconds to keep event history (5 min)
_HISTORY_MAX_LEN = 500  # max events retained per workflow
_pub_redis: aioredis.Redis | None = None


def _channel(workflow_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{workflow_id}"


def _history_key(workflow_id: str) -> str:
    return f"{_HISTORY_PREFIX}{workflow_id}"


def _counter_key(workflow_id: str) -> str:
    return f"{_COUNTER_PREFIX}{workflow_id}"


async def _get_pub_redis() -> aioredis.Redis:
    """Return the shared publisher Redis connection, reconnecting if needed."""
    global _pub_redis
    if _pub_redis is None:
        _pub_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _pub_redis


async def publish(workflow_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Publish an event to a workflow's Redis channel.

    Each event is assigned a monotonic ``id`` and appended to a capped
    history list so reconnecting SSE clients can replay missed events.
    """
    global _pub_redis
    for attempt in range(2):
        try:
            r = await _get_pub_redis()
            # Assign monotonic event ID
            event_id = await r.incr(_counter_key(workflow_id))
            await r.expire(_counter_key(workflow_id), _HISTORY_TTL)

            payload = json.dumps(
                {
                    "id": event_id,
                    "type": event_type,
                    "data": data,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                default=str,
            )

            pipe = r.pipeline()
            pipe.publish(_channel(workflow_id), payload)
            # Store in history for replay
            hkey = _history_key(workflow_id)
            pipe.rpush(hkey, payload)
            pipe.ltrim(hkey, -_HISTORY_MAX_LEN, -1)
            pipe.expire(hkey, _HISTORY_TTL)
            if event_type == "status":
                cutoff_ms = int(
                    (datetime.now(UTC).timestamp() - settings.task_status_event_ttl_seconds)
                    * 1000
                )
                pipe.xadd(
                    _TASK_STATUS_STREAM,
                    {
                        "workflow_id": workflow_id,
                        "payload": payload,
                    },
                )
                pipe.xtrim(
                    _TASK_STATUS_STREAM,
                    minid=f"{cutoff_ms}-0",
                    approximate=True,
                )
                pipe.expire(
                    _TASK_STATUS_STREAM,
                    settings.task_status_event_ttl_seconds,
                )
            await pipe.execute()
            return
        except Exception:
            if _pub_redis is not None:
                try:
                    await _pub_redis.aclose()
                except Exception:
                    pass
                _pub_redis = None
    logger.warning("Failed to publish event for workflow %s", workflow_id)


async def get_events_since(
    workflow_id: str, last_event_id: int
) -> list[str]:
    """Return all stored events with id > *last_event_id*.

    Used by the SSE endpoint to replay missed events on reconnect.
    """
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw_events = await r.lrange(_history_key(workflow_id), 0, -1)
        result: list[str] = []
        for raw in raw_events:
            try:
                evt = json.loads(raw)
                if evt.get("id", 0) > last_event_id:
                    result.append(raw)
            except (json.JSONDecodeError, TypeError):
                continue
        return result
    finally:
        await r.aclose()


async def subscribe(
    workflow_id: str, last_event_id: int | None = None
) -> AsyncGenerator[str | None, None]:
    """Subscribe to a workflow's events via Redis pub/sub.

    If *last_event_id* is provided, first replays any stored events with a
    higher ID before switching to live pub/sub — ensuring no events are lost
    on reconnection.

    To avoid dropping events published between the history read and the
    subscribe call, we establish the pub/sub subscription *first*, then
    replay from history, and finally switch to live — deduplicating any
    events that arrive in both the replay and the live stream.

    Yields JSON payload strings, or None on timeout (for keepalive signalling).
    Automatically cleans up the subscription when the generator is closed.
    """
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(_channel(workflow_id))

    # Track the highest replayed ID so live events can be deduplicated
    seen_up_to: int = 0

    try:
        # ── Replay missed events ─────────────────────────────────────────
        if last_event_id is not None:
            missed = await get_events_since(workflow_id, last_event_id)
            for payload in missed:
                yield payload
                try:
                    evt = json.loads(payload)
                    eid = evt.get("id", 0)
                    if eid > seen_up_to:
                        seen_up_to = eid
                except (json.JSONDecodeError, TypeError):
                    pass

        # ── Live subscription ────────────────────────────────────────────
        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=30.0
            )
            if msg is not None:
                data = msg["data"]
                # Deduplicate against replayed events
                if seen_up_to:
                    try:
                        evt = json.loads(data)
                        if evt.get("id", 0) <= seen_up_to:
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                    seen_up_to = 0  # done deduplicating
                yield data
            else:
                yield None  # keepalive signal
    finally:
        await pubsub.unsubscribe(_channel(workflow_id))
        await pubsub.aclose()
        await r.aclose()


# ── Halt signal ──────────────────────────────────────────────────────────────

_HALT_KEY_PREFIX = "workflow:halt:"


async def set_halt(workflow_id: str) -> None:
    """Set a halt signal for a running workflow (expires after 5 min)."""
    global _pub_redis
    if _pub_redis is None:
        _pub_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await _pub_redis.set(f"{_HALT_KEY_PREFIX}{workflow_id}", "1", ex=300)


async def check_halt(workflow_id: str) -> bool:
    """Check whether a halt signal has been set for a workflow."""
    global _pub_redis
    if _pub_redis is None:
        _pub_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    val = await _pub_redis.get(f"{_HALT_KEY_PREFIX}{workflow_id}")
    return val is not None


async def clear_halt(workflow_id: str) -> None:
    """Clear the halt signal for a workflow."""
    global _pub_redis
    if _pub_redis is None:
        _pub_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await _pub_redis.delete(f"{_HALT_KEY_PREFIX}{workflow_id}")
