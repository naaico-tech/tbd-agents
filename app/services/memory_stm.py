"""Short-Term Memory (STM) layer backed by Redis.

Stores the last N memories per agent as a Redis sorted-set (scored by
timestamp) for fast context injection, while MongoDB remains the
authoritative Long-Term Memory (LTM) store.
"""

import json
import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "stm:"
_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _agent_key(agent_id: str) -> str:
    return f"{_KEY_PREFIX}{agent_id}"


def _encode_memory(mem_dict: dict) -> str:
    return json.dumps(mem_dict, default=str)


def _decode_memory(raw: str) -> dict:
    return json.loads(raw)


async def push_memory(agent_id: str, memory: dict) -> None:
    """Add or update a memory in the agent's STM sorted set.

    The score is the updated_at timestamp (epoch seconds).
    If the set exceeds ``stm_max_entries`` the oldest entries are trimmed.
    """
    r = await _get_redis()
    key = _agent_key(agent_id)

    # Use (scope, mem_key) as dedup: remove any prior entry with same identity
    identity = json.dumps({"scope": memory.get("scope"), "key": memory.get("key")})

    # Remove old entry if exists (scan is bounded by stm_max_entries + small margin)
    existing = await r.zrange(key, 0, -1)
    for raw in existing:
        entry = _decode_memory(raw)
        if entry.get("scope") == memory.get("scope") and entry.get("key") == memory.get("key"):
            await r.zrem(key, raw)
            break

    ts = memory.get("updated_at")
    if isinstance(ts, datetime):
        score = ts.timestamp()
    elif isinstance(ts, str):
        score = datetime.fromisoformat(ts).timestamp()
    else:
        score = datetime.now(UTC).timestamp()

    await r.zadd(key, {_encode_memory(memory): score})

    # Trim to keep only the most recent N entries
    max_entries = settings.stm_max_entries
    count = await r.zcard(key)
    if count > max_entries:
        await r.zremrangebyrank(key, 0, count - max_entries - 1)


async def get_recent_memories(agent_id: str, limit: int | None = None) -> list[dict]:
    """Return the most recent STM entries for an agent, newest first."""
    r = await _get_redis()
    key = _agent_key(agent_id)
    n = limit or settings.stm_max_entries
    raw_list = await r.zrevrange(key, 0, n - 1)
    return [_decode_memory(raw) for raw in raw_list]


async def remove_memory(agent_id: str, scope: str, mem_key: str) -> None:
    """Remove a specific memory from the agent's STM."""
    r = await _get_redis()
    key = _agent_key(agent_id)
    existing = await r.zrange(key, 0, -1)
    for raw in existing:
        entry = _decode_memory(raw)
        if entry.get("scope") == scope and entry.get("key") == mem_key:
            await r.zrem(key, raw)
            return


async def clear_agent_stm(agent_id: str) -> None:
    """Remove all STM entries for an agent."""
    r = await _get_redis()
    await r.delete(_agent_key(agent_id))


async def warmup_all_agents() -> int:
    """Load recent memories for every agent from MongoDB into Redis STM.

    Called once at application startup so that the first agent execution
    can read its context from Redis rather than hitting MongoDB.
    Returns the number of agents warmed up.
    """
    from app.models.memory import Memory

    pipeline = [
        {"$sort": {"updated_at": -1}},
        {"$group": {"_id": "$agent_id", "memories": {"$push": "$$ROOT"}}},
    ]
    collection = Memory.get_motor_collection()
    cursor = collection.aggregate(pipeline)

    r = await _get_redis()
    max_n = settings.stm_max_entries
    agent_count = 0

    async for group in cursor:
        agent_id = group["_id"]
        key = _agent_key(agent_id)

        # Clear existing STM for this agent
        await r.delete(key)

        # Take only the most recent N
        memories = group["memories"][:max_n]
        if not memories:
            continue

        mapping: dict[str, float] = {}
        for doc in memories:
            ts = doc.get("updated_at", datetime.now(UTC))
            score = ts.timestamp() if isinstance(ts, datetime) else datetime.now(UTC).timestamp()
            mem_dict = {
                "scope": doc.get("scope", "agent"),
                "key": doc.get("key", ""),
                "value": doc.get("value", ""),
                "agent_id": agent_id,
                "updated_at": ts.isoformat() if isinstance(ts, datetime) else str(ts),
            }
            mapping[_encode_memory(mem_dict)] = score

        if mapping:
            await r.zadd(key, mapping)
            # Trim just in case
            count = await r.zcard(key)
            if count > max_n:
                await r.zremrangebyrank(key, 0, count - max_n - 1)

        agent_count += 1

    logger.info("STM warmup complete: loaded memories for %d agent(s)", agent_count)
    return agent_count


async def close() -> None:
    """Close the Redis connection (for graceful shutdown)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
