"""Redis-backed progress counters for index jobs.

Two flavours of API are exposed:

* ``async def`` helpers — used by the FastAPI request handlers and the SSE
  streamer; they use ``redis.asyncio``.
* ``*_sync`` helpers — used by Celery tasks (which are sync) so we don't have
  to spin up an event loop just to bump a counter.

Hash key: ``index:job:{job_id}`` with fields:

    files_total, files_done, files_failed,
    chunks_total, chunks_done, bytes_done,
    phase, current_file, updated_at  (epoch ms)

Cancel flag key: ``index:job:{job_id}:cancel`` (set to ``"1"`` when cancel
requested). TTL on the hash defaults to 1 hour after a terminal state via
:func:`clear`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import redis as _redis_sync_pkg
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_HASH_PREFIX = "index:job:"
_CANCEL_SUFFIX = ":cancel"
_TERMINAL_TTL_SECONDS = 3600  # keep snapshot 1 h after job finishes

_COUNTER_FIELDS = (
    "files_total",
    "files_done",
    "files_failed",
    "chunks_total",
    "chunks_done",
    "bytes_done",
)

# ── Connection helpers ──────────────────────────────────────────────────────

_async_client: aioredis.Redis | None = None
_async_client_loop: asyncio.AbstractEventLoop | None = None


def _redis() -> aioredis.Redis:
    """Return an async Redis client valid for the *current* event loop.

    Celery tasks use asyncio.run() which creates a new loop each time.
    Caching across loops causes 'Future attached to different loop'.
    We recreate the client whenever the running loop changes.
    """
    global _async_client, _async_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if _async_client is None or _async_client_loop is not current_loop:
        _async_client = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        _async_client_loop = current_loop
    return _async_client


def _redis_sync() -> _redis_sync_pkg.Redis:
    """Build a sync Redis client — Celery tasks are sync."""
    return _redis_sync_pkg.Redis.from_url(
        settings.redis_url, decode_responses=True
    )


def _key(job_id: str) -> str:
    return f"{_HASH_PREFIX}{job_id}"


def _cancel_key(job_id: str) -> str:
    return f"{_HASH_PREFIX}{job_id}{_CANCEL_SUFFIX}"


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Async API ───────────────────────────────────────────────────────────────


async def init_progress(
    job_id: str, files_total: int = 0, chunks_total: int = 0
) -> None:
    """Initialise the hash with totals and zeroed counters."""
    r = _redis()
    mapping: dict[str, Any] = {
        "files_total": int(files_total),
        "files_done": 0,
        "files_failed": 0,
        "chunks_total": int(chunks_total),
        "chunks_done": 0,
        "bytes_done": 0,
        "phase": "queued",
        "current_file": "",
        "updated_at": _now_ms(),
    }
    await r.hset(_key(job_id), mapping=mapping)


async def incr(
    job_id: str,
    *,
    files_done: int = 0,
    chunks_done: int = 0,
    bytes_done: int = 0,
    files_failed: int = 0,
) -> None:
    r = _redis()
    key = _key(job_id)
    pipe = r.pipeline()
    if files_done:
        pipe.hincrby(key, "files_done", files_done)
    if chunks_done:
        pipe.hincrby(key, "chunks_done", chunks_done)
    if bytes_done:
        pipe.hincrby(key, "bytes_done", bytes_done)
    if files_failed:
        pipe.hincrby(key, "files_failed", files_failed)
    pipe.hset(key, "updated_at", _now_ms())
    await pipe.execute()


async def set_phase(
    job_id: str, phase: str, current_file: str | None = None
) -> None:
    r = _redis()
    mapping: dict[str, Any] = {"phase": phase, "updated_at": _now_ms()}
    if current_file is not None:
        mapping["current_file"] = current_file
    await r.hset(_key(job_id), mapping=mapping)


async def snapshot(job_id: str) -> dict:
    r = _redis()
    raw = await r.hgetall(_key(job_id))
    return _normalise(raw)


async def clear(job_id: str) -> None:
    """Apply a 1-hour TTL on the hash + cancel flag (terminal state)."""
    r = _redis()
    pipe = r.pipeline()
    pipe.expire(_key(job_id), _TERMINAL_TTL_SECONDS)
    pipe.expire(_cancel_key(job_id), _TERMINAL_TTL_SECONDS)
    await pipe.execute()


async def is_cancelled(job_id: str) -> bool:
    r = _redis()
    return bool(await r.exists(_cancel_key(job_id)))


async def request_cancel(job_id: str) -> None:
    r = _redis()
    await r.set(_cancel_key(job_id), "1")


# ── Sync API (Celery workers) ───────────────────────────────────────────────


def init_progress_sync(
    job_id: str, files_total: int = 0, chunks_total: int = 0
) -> None:
    r = _redis_sync()
    try:
        r.hset(
            _key(job_id),
            mapping={
                "files_total": int(files_total),
                "files_done": 0,
                "files_failed": 0,
                "chunks_total": int(chunks_total),
                "chunks_done": 0,
                "bytes_done": 0,
                "phase": "queued",
                "current_file": "",
                "updated_at": _now_ms(),
            },
        )
    finally:
        try:
            r.close()
        except Exception:
            pass


def incr_sync(
    job_id: str,
    *,
    files_done: int = 0,
    chunks_done: int = 0,
    bytes_done: int = 0,
    files_failed: int = 0,
) -> None:
    r = _redis_sync()
    try:
        key = _key(job_id)
        pipe = r.pipeline()
        if files_done:
            pipe.hincrby(key, "files_done", files_done)
        if chunks_done:
            pipe.hincrby(key, "chunks_done", chunks_done)
        if bytes_done:
            pipe.hincrby(key, "bytes_done", bytes_done)
        if files_failed:
            pipe.hincrby(key, "files_failed", files_failed)
        pipe.hset(key, "updated_at", _now_ms())
        pipe.execute()
    finally:
        try:
            r.close()
        except Exception:
            pass


def set_phase_sync(
    job_id: str, phase: str, current_file: str | None = None
) -> None:
    r = _redis_sync()
    try:
        mapping: dict[str, Any] = {"phase": phase, "updated_at": _now_ms()}
        if current_file is not None:
            mapping["current_file"] = current_file
        r.hset(_key(job_id), mapping=mapping)
    finally:
        try:
            r.close()
        except Exception:
            pass


def snapshot_sync(job_id: str) -> dict:
    r = _redis_sync()
    try:
        raw = r.hgetall(_key(job_id))
        return _normalise(raw)
    finally:
        try:
            r.close()
        except Exception:
            pass


def is_cancelled_sync(job_id: str) -> bool:
    r = _redis_sync()
    try:
        return bool(r.exists(_cancel_key(job_id)))
    finally:
        try:
            r.close()
        except Exception:
            pass


# ── Helpers ─────────────────────────────────────────────────────────────────


def _normalise(raw: dict[str, Any] | None) -> dict:
    """Coerce Redis string values into ints / strings expected by callers."""
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else v
        if key in _COUNTER_FIELDS or key == "updated_at":
            try:
                out[key] = int(val)
            except (TypeError, ValueError):
                out[key] = 0
        else:
            out[key] = val
    return out
