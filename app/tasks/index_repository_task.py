"""Celery tasks for the chord-based indexing pipeline (PR3).

The pipeline is split into three tasks that fan out work to dedicated queues:

* :func:`run_index_repository_job` (queue ``indexing``) — orchestrator. Syncs
  the repo, discovers changes, shards the manifest, and kicks off a Celery
  ``chord(group(index_shard.s(...) for s in shards), finalize_index_job.s(...))``.
  The orchestrator returns immediately after launching the chord; finalisation
  happens out-of-band in :func:`finalize_index_job`.
* :func:`index_shard` (queue ``embeddings``) — per-shard worker. Reads,
  chunks, embeds, and upserts a *subset* of the manifest. Never touches
  ``CodeRepository`` summary state — that's the finaliser's job. Safe to
  retry: deterministic point ids + ``IndexedFile`` upsert make shards
  idempotent.
* :func:`finalize_index_job` (queue ``indexing``) — chord callback.
  Aggregates per-shard counters, calls
  :meth:`code_repository_manager.finalize_repo` exactly once, and transitions
  the :class:`IndexJob` ``embedding → committed → done``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import traceback
from datetime import UTC, datetime
from typing import Any

from celery import chord, group

from app.celery_app import celery
from app.services import index_progress

logger = logging.getLogger(__name__)

_TRACEBACK_MAX = 4096  # truncate stored tracebacks to ~4 KB

# ── Sharding tunables ────────────────────────────────────────────────────────
# Override via env at deploy time to fit cluster size / file mix.
MAX_SHARDS: int = int(os.environ.get("INDEX_MAX_SHARDS", "16"))
FILES_PER_SHARD: int = int(os.environ.get("INDEX_FILES_PER_SHARD", "50"))


# ── Sharding helper ──────────────────────────────────────────────────────────


def _shard_count(n_files: int) -> int:
    """Pick a shard count: 1 ≤ N ≤ MAX_SHARDS, ≈ ceil(files / FILES_PER_SHARD)."""
    if n_files <= 0:
        return 0
    per = max(1, FILES_PER_SHARD)
    return max(1, min(MAX_SHARDS, math.ceil(n_files / per)))


def _shard_index_for_path(file_path: str, n_shards: int) -> int:
    """Stable assignment of a file path to a shard via SHA1 mod N.

    Stable across runs → same files end up on the same workers (cache locality
    for tree-sitter parsers, embedding warm caches, etc.).
    """
    if n_shards <= 1:
        return 0
    digest = hashlib.sha1(file_path.encode("utf-8")).hexdigest()
    return int(digest, 16) % n_shards


def _build_shards(
    changes: list[Any], n_shards: int
) -> list[list[dict]]:
    """Bucket :class:`FileChange` objects into ``n_shards`` plain-dict shards.

    Returned payloads are JSON-serialisable so they round-trip through
    Celery's default JSON serializer.
    """
    if n_shards <= 0:
        return []
    buckets: list[list[dict]] = [[] for _ in range(n_shards)]
    for change in changes:
        idx = _shard_index_for_path(change.path, n_shards)
        buckets[idx].append(
            {
                "path": change.path,
                "blob_sha": change.blob_sha,
                "change": change.change,
                "size": change.size,
            }
        )
    # Drop empty buckets — chord/group complains less and the count is exact.
    return [b for b in buckets if b]


def _file_changes_from_payload(payload: list[dict]) -> list[Any]:
    """Reconstruct :class:`FileChange` objects from a shard payload."""
    from app.services.code_repository_manager import FileChange

    return [
        FileChange(
            path=item["path"],
            blob_sha=item.get("blob_sha", "") or "",
            change=item["change"],
            size=int(item.get("size") or 0),
        )
        for item in payload
    ]


# ── Orchestrator ─────────────────────────────────────────────────────────────


@celery.task(name="run_index_repository_job", bind=True, max_retries=0)
def run_index_repository_job(self, job_id: str, force_full: bool = False) -> dict | None:
    """Drive a single :class:`IndexJob` through discovery + chord fan-out.

    Phases:
        queued → discovering (sync + diff) → embedding (chord launched)

    Finalisation (``embedding → committed → done``) happens in
    :func:`finalize_index_job` once every shard succeeds. On any exception
    *before* the chord is launched, the job is marked ``failed``.

    Pass ``force_full=True`` to bypass the incremental-diff base-SHA lookup
    and force a complete re-index (useful when globs change without a new commit).
    """
    worker = getattr(self.request, "hostname", None)
    try:
        return asyncio.run(_run(job_id, worker, force_full=force_full))
    except Exception:  # pragma: no cover - logged below
        logger.exception("IndexJob %s crashed", job_id)
        try:
            asyncio.run(_mark_failed(job_id, traceback.format_exc()))
        except Exception:
            logger.exception("Failed to mark IndexJob %s failed", job_id)
        raise


async def _run(job_id: str, worker: str | None, *, force_full: bool = False) -> dict | None:
    from beanie import PydanticObjectId

    from app.db import init_db
    from app.models.code_repository import CodeRepository, CodeRepositoryStatus
    from app.models.index_job import IndexJob
    from app.services.code_repository_manager import (
        code_repository_manager,
        discover_changes,
    )

    await init_db()

    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job:
        logger.error("IndexJob %s not found", job_id)
        return None

    repo = await CodeRepository.get(job.repo_id)
    if not repo:
        await _set_failed(job, message=f"CodeRepository {job.repo_id} not found")
        return None

    # ── Initialise progress channel ────────────────────────────────────────
    await index_progress.init_progress(job_id)
    await index_progress.set_phase(job_id, "discovering", current_file="")

    job.state = "discovering"
    job.current_phase = "discovering"
    job.started_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    await job.save()

    # Use the last SUCCESSFULLY indexed commit as diff base.
    # sync() persists last_commit_sha even when indexing fails; using it
    # as base would produce an empty diff on retry (base == head).
    # When force_full=True we skip the lookup entirely and do a full re-index
    # (useful after include/exclude glob changes without a new commit).
    from app.models.index_job import IndexJob as _IndexJob

    if force_full:
        base_sha: str | None = None
    else:
        # Snapshot the pre-sync SHA as a fallback for environments where Beanie
        # is not fully initialised (e.g. unit tests without a live MongoDB).
        _pre_sync_sha: str | None = repo.last_commit_sha or None
        try:
            last_done = await _IndexJob.find(
                {"repo_id": job.repo_id, "state": "done"}
            ).sort("-finished_at").first_or_none()
            base_sha = last_done.head_commit_sha if last_done else None
        except Exception:
            # Beanie unavailable or query error — use the pre-sync snapshot.
            base_sha = _pre_sync_sha

    # ── Sync (clone / fetch) ───────────────────────────────────────────────
    await code_repository_manager.sync(repo, force=True)

    if repo.status == CodeRepositoryStatus.ERROR:
        await _set_failed(
            job,
            message=f"sync_failed: {repo.last_error or 'unknown'}",
        )
        return None

    head_sha = repo.last_commit_sha or ""
    job.base_commit_sha = base_sha
    job.head_commit_sha = head_sha or None
    await job.save()

    # ── Discover changes ──────────────────────────────────────────────────
    try:
        manifest = await discover_changes(repo, base_sha, head_sha)
    except Exception as exc:
        await _set_failed(
            job,
            message=f"discover_failed: {str(exc)[:400]}",
            tb=traceback.format_exc(),
        )
        return None

    job.kind = "incremental" if (manifest.base_sha is not None) else "full"
    files_total = len(manifest.changes)
    await index_progress.init_progress(
        job_id, files_total=files_total, chunks_total=0
    )

    # ── Empty manifest fast path: finalise inline, never launch a chord ───
    if not manifest.changes:
        await index_progress.set_phase(job_id, "embedding", current_file="")
        await code_repository_manager.finalize_repo(repo, head_sha)
        await _mark_done_empty(job, head_sha=head_sha)
        await index_progress.set_phase(job_id, "done")
        await index_progress.clear(job_id)
        _ = worker
        return {
            "job_id": job_id,
            "shard_count": 0,
            "chord_id": None,
            "empty": True,
        }

    # ── Build shards ──────────────────────────────────────────────────────
    n_shards = _shard_count(files_total)
    shards = _build_shards(manifest.changes, n_shards)
    actual_shards = len(shards)  # post-empty-bucket pruning

    job.shard_count = actual_shards
    job.shards_done = 0
    job.state = "embedding"
    job.current_phase = "embedding"
    job.updated_at = datetime.now(UTC)
    await job.save()
    await index_progress.set_phase(job_id, "embedding")

    # ── Kick off chord ────────────────────────────────────────────────────
    header = group(index_shard.s(job_id, shard) for shard in shards)
    callback = finalize_index_job.s(job_id)
    async_result = chord(header, callback).apply_async()
    chord_id = getattr(async_result, "id", None)

    logger.info(
        "IndexJob %s: launched chord with %d shards (chord_id=%s)",
        job_id, actual_shards, chord_id,
    )
    _ = worker
    return {
        "job_id": job_id,
        "shard_count": actual_shards,
        "chord_id": chord_id,
        "empty": False,
    }


# ── Per-shard worker ─────────────────────────────────────────────────────────


@celery.task(
    bind=True,
    name="app.tasks.index_repository_task.index_shard",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def index_shard(self, job_id: str, shard: list[dict]) -> dict:
    """Index a SUBSET of the manifest on the embeddings queue.

    Returns the per-shard counter dict produced by
    :meth:`CodeRepositoryManager.index_changes`. Safe to retry: deterministic
    point ids + ``IndexedFile`` upsert make individual files idempotent.
    """
    _ = self  # placeholder for future telemetry
    try:
        return asyncio.run(_run_shard(job_id, shard))
    except Exception:
        logger.exception("index_shard %s failed for job %s", shard[:1], job_id)
        raise


async def _run_shard(job_id: str, shard_payload: list[dict]) -> dict:
    from beanie import PydanticObjectId

    from app.db import init_db
    from app.models.code_repository import CodeRepository
    from app.models.index_job import IndexJob
    from app.services.code_repository_manager import (
        Manifest,
        code_repository_manager,
    )

    await init_db()

    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job:
        logger.warning("index_shard: IndexJob %s missing — skipping", job_id)
        return _empty_shard_result(reason="job_missing")

    repo = await CodeRepository.get(job.repo_id)
    if not repo:
        logger.warning(
            "index_shard: repo %s missing for job %s", job.repo_id, job_id
        )
        return _empty_shard_result(reason="repo_missing")

    head_sha = job.head_commit_sha or repo.last_commit_sha or ""

    # Honour cancellation eagerly — don't bother starting if cancelled.
    if index_progress.is_cancelled_sync(job_id):
        return _empty_shard_result(reason="cancelled", cancelled=True)

    # Reconstruct FileChange objects, then drop any cancelled mid-way.
    changes_all = _file_changes_from_payload(shard_payload)
    cancelled = False
    processed: list[Any] = []
    for change in changes_all:
        if index_progress.is_cancelled_sync(job_id):
            cancelled = True
            break
        processed.append(change)

    if not processed:
        return _empty_shard_result(reason="cancelled", cancelled=True)

    sub_manifest = Manifest(
        head_sha=head_sha, base_sha=None, changes=processed
    )

    result = await code_repository_manager.index_changes(
        repo, sub_manifest, job_id=job_id, finalize=False
    )
    result["shard_size"] = len(processed)
    result["cancelled"] = cancelled
    return result


def _empty_shard_result(*, reason: str, cancelled: bool = False) -> dict:
    return {
        "indexed": True,
        "added": 0,
        "modified": 0,
        "deleted": 0,
        "chunks_done": 0,
        "files_failed": 0,
        "shard_size": 0,
        "cancelled": cancelled,
        "reason": reason,
    }


# ── Chord callback ───────────────────────────────────────────────────────────


@celery.task(
    bind=True,
    name="app.tasks.index_repository_task.finalize_index_job",
    max_retries=0,
)
def finalize_index_job(
    self, shard_results: list[dict], job_id: str
) -> dict:
    """Aggregate shard counters and finalise the :class:`IndexJob`.

    Runs once (chord callback). Transitions the job
    ``embedding → committed → done`` and calls
    :meth:`CodeRepositoryManager.finalize_repo` exactly once so summary fields
    on the parent ``CodeRepository`` are recomputed without shard races.
    """
    _ = self
    try:
        return asyncio.run(_run_finalize(shard_results or [], job_id))
    except Exception:
        logger.exception("finalize_index_job failed for %s", job_id)
        try:
            asyncio.run(_mark_failed(job_id, traceback.format_exc()))
        except Exception:
            logger.exception(
                "finalize_index_job: failed to mark %s failed", job_id
            )
        raise


async def _run_finalize(shard_results: list[dict], job_id: str) -> dict:
    from beanie import PydanticObjectId

    from app.db import init_db
    from app.models.code_repository import CodeRepository
    from app.models.index_job import (
        IndexJob,
        IndexJobCounters,
        IndexJobError,
    )
    from app.services.code_repository_manager import code_repository_manager

    await init_db()

    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job:
        logger.error("finalize_index_job: IndexJob %s not found", job_id)
        return {"finalized": False, "reason": "job_missing"}

    repo = await CodeRepository.get(job.repo_id)
    if not repo:
        await _set_failed(
            job, message=f"CodeRepository {job.repo_id} not found"
        )
        return {"finalized": False, "reason": "repo_missing"}

    # ── Aggregate ─────────────────────────────────────────────────────────
    totals = {
        "added": 0,
        "modified": 0,
        "deleted": 0,
        "chunks_done": 0,
        "files_failed": 0,
    }
    any_cancelled = False
    error_msg: str | None = None
    for r in shard_results:
        if not isinstance(r, dict):
            continue
        if r.get("cancelled"):
            any_cancelled = True
        if r.get("indexed") is False:
            error_msg = r.get("error") or r.get("reason") or "shard_failed"
        for k in totals:
            totals[k] += int(r.get(k, 0) or 0)

    head_sha = job.head_commit_sha or repo.last_commit_sha or ""

    job.state = "committed"
    job.current_phase = "committed"
    job.shards_done = sum(1 for r in shard_results if isinstance(r, dict))
    job.updated_at = datetime.now(UTC)
    await job.save()
    await index_progress.set_phase(job_id, "committed")

    # ── Finalise repo summary (exactly once) ──────────────────────────────
    try:
        await code_repository_manager.finalize_repo(repo, head_sha)
    except Exception as exc:
        await _set_failed(
            job,
            message=f"finalize_failed: {str(exc)[:400]}",
            tb=traceback.format_exc(),
        )
        return {"finalized": False, "reason": "finalize_failed"}

    # ── Merge Redis counters → Mongo ──────────────────────────────────────
    snap = await index_progress.snapshot(job_id)
    job.counters = IndexJobCounters(
        files_total=int(snap.get("files_total") or 0),
        files_done=int(snap.get("files_done") or 0),
        files_failed=int(snap.get("files_failed") or totals["files_failed"]),
        chunks_total=int(snap.get("chunks_total") or 0),
        chunks_done=int(snap.get("chunks_done") or totals["chunks_done"]),
        bytes_done=int(snap.get("bytes_done") or 0),
        files_added=totals["added"],
        files_modified=totals["modified"],
        files_deleted=totals["deleted"],
    )

    if any_cancelled:
        job.state = "cancelled"
        job.current_phase = "cancelled"
    elif error_msg:
        job.state = "failed"
        job.current_phase = "failed"
        job.error = IndexJobError(message=error_msg)
    else:
        job.state = "done"
        job.current_phase = "done"

    job.finished_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    await job.save()

    # Mirror back to the parent CodeRepository.
    repo.last_indexed_job_id = str(job.id)
    await repo.save()

    await index_progress.set_phase(job_id, job.current_phase)
    await index_progress.clear(job_id)

    return {
        "finalized": True,
        "state": job.state,
        "totals": totals,
        "shards_done": job.shards_done,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _mark_done_empty(job, *, head_sha: str) -> None:
    """Mark an empty-manifest job ``done`` without launching any shards."""
    from app.models.index_job import IndexJobCounters

    job.kind = job.kind or "full"
    job.shard_count = 0
    job.shards_done = 0
    job.head_commit_sha = head_sha or job.head_commit_sha
    job.state = "done"
    job.current_phase = "done"
    job.counters = IndexJobCounters(files_total=0)
    job.finished_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    await job.save()


async def _set_failed(
    job, *, message: str, tb: str | None = None
) -> None:
    from app.models.index_job import IndexJobError

    job.state = "failed"
    job.current_phase = "failed"
    job.error = IndexJobError(
        message=message, traceback=(tb or "")[:_TRACEBACK_MAX] or None
    )
    job.finished_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    await job.save()


async def _mark_failed(job_id: str, tb: str) -> None:
    from beanie import PydanticObjectId

    from app.db import init_db
    from app.models.index_job import TERMINAL_STATES, IndexJob

    await init_db()
    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job or job.state in TERMINAL_STATES:
        return
    await _set_failed(job, message="task_crashed", tb=tb)
