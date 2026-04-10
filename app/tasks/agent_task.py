"""Celery task that runs the Copilot agent engine in a worker process."""

import asyncio
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="run_agent_task", bind=True, max_retries=1)
def run_agent_task(self, workflow_id: str, user_prompt: str, github_token: str):
    """Execute the agent engine inside an asyncio event loop.

    Each invocation creates a fresh event loop via asyncio.run(), initialises
    a Beanie/Motor DB connection, loads the Workflow document, and delegates
    to `run_agent()`.
    """
    try:
        asyncio.run(_execute(workflow_id, user_prompt, github_token))
    except Exception:
        # Best-effort: mark the workflow as failed if the task crashes
        try:
            asyncio.run(_mark_failed(workflow_id))
        except Exception:
            logger.exception("Failed to mark workflow %s as failed", workflow_id)
        raise


async def _execute(workflow_id: str, user_prompt: str, github_token: str):
    """Async entry point — initialises DB and runs the agent."""
    from beanie import PydanticObjectId

    from app.core.agent_engine import run_agent
    from app.db import init_db
    from app.models.workflow import Workflow

    await init_db()
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        logger.error("Workflow %s not found", workflow_id)
        return
    await run_agent(wf, user_prompt, github_token)


async def _mark_failed(workflow_id: str):
    """Mark a workflow as failed when the Celery task crashes unexpectedly."""
    from beanie import PydanticObjectId

    from app.core import event_bus
    from app.db import init_db
    from app.models.workflow import Workflow, WorkflowStatus

    await init_db()
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if wf and wf.status not in (
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.MAX_TURNS_REACHED,
    ):
        wf.status = WorkflowStatus.FAILED
        await wf.save()
        await event_bus.publish(
            workflow_id, "status", {"status": "failed", "current_turn": wf.current_turn}
        )
