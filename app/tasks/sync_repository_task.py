"""Celery task: sync (clone / fetch) a single :class:`CodeRepository`.

Introduced as part of ``worker-only-repo-clones``: the API container no
longer touches the repo working tree, so ``POST /sync`` enqueues this
task instead of calling ``code_repository_manager.sync`` inline.

The task is intentionally minimal — sync state is already persisted on
the :class:`CodeRepository` document by ``code_repository_manager.sync``
(``status`` / ``last_synced_at`` / ``last_commit_sha`` / ``last_error``),
so we don't introduce a second job document for it.
"""

from __future__ import annotations

import asyncio
import logging
import traceback

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="run_sync_repository_job", bind=True, max_retries=0)
def run_sync_repository_job(self, repo_id: str) -> dict:
    """Clone-or-fetch a single repository on a worker.

    Returns a small status dict for the Celery result backend; the
    authoritative sync state lives on the :class:`CodeRepository` doc.
    """
    _ = self  # bind=True; reserved for future telemetry / retries
    try:
        return asyncio.run(_run(repo_id))
    except Exception as exc:  # pragma: no cover - logged
        logger.exception("Sync job for repo %s crashed", repo_id)
        return {
            "repo_id": repo_id,
            "ok": False,
            "error": str(exc)[:500],
            "traceback": traceback.format_exc()[:4096],
        }


async def _run(repo_id: str) -> dict:
    from beanie import PydanticObjectId

    from app.db import init_db
    from app.models.code_repository import CodeRepository
    from app.services.code_repository_manager import code_repository_manager

    await init_db()

    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        logger.error("CodeRepository %s not found for sync job", repo_id)
        return {"repo_id": repo_id, "ok": False, "error": "repo_not_found"}

    await code_repository_manager.sync(repo, force=True)
    return {
        "repo_id": repo_id,
        "ok": True,
        "status": str(repo.status),
        "local_path": repo.local_path,
        "last_commit_sha": repo.last_commit_sha,
        "last_error": repo.last_error,
    }
