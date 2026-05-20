"""Celery tasks for asynchronous CodeGraph repository indexing."""

import asyncio
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="codegraph.index_repo", max_retries=2, default_retry_delay=30)
def index_repo_task(self, repo_id: str, repo_url: str, name: str) -> dict:
    """Clone and index a repository in the background.

    Called by POST /api/codegraph/repos when async_index=True.
    Retries up to 2 times on failure with 30s delay.
    """

    async def _run():
        # Imported inside the function to avoid circular imports and event-loop
        # issues that arise from importing at module level in a Celery worker.
        from app.services.codegraph_service import codegraph_service

        await codegraph_service.index_repository(
            repo_url=repo_url, name=name, repo_id=repo_id
        )

    try:
        asyncio.run(_run())
        return {"status": "done", "repo_id": repo_id}
    except Exception as exc:
        logger.exception("index_repo_task failed for repo_id=%s", repo_id)
        raise self.retry(exc=exc)
