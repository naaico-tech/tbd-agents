"""In-memory pub/sub event bus for SSE streaming.

Allows agent_engine to publish real-time events (logs, messages, usage, status)
and SSE endpoints to subscribe per-workflow.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# workflow_id -> list of subscriber queues
_subscribers: dict[str, list[asyncio.Queue]] = {}


def subscribe(workflow_id: str) -> asyncio.Queue:
    """Register a new subscriber for a workflow's events."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(workflow_id, []).append(queue)
    return queue


def unsubscribe(workflow_id: str, queue: asyncio.Queue) -> None:
    """Remove a subscriber queue."""
    subs = _subscribers.get(workflow_id)
    if subs:
        try:
            subs.remove(queue)
        except ValueError:
            pass
        if not subs:
            del _subscribers[workflow_id]


async def publish(workflow_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Fan out an event to all subscribers of a workflow."""
    subs = _subscribers.get(workflow_id)
    if not subs:
        return
    payload = json.dumps(
        {"type": event_type, "data": data, "timestamp": datetime.now(UTC).isoformat()},
        default=str,
    )
    for queue in list(subs):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("Subscriber queue full for workflow %s, dropping event", workflow_id)
