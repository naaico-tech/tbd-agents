"""Celery task that runs the Copilot agent engine in a worker process."""

import asyncio
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="run_agent_task", bind=True, max_retries=1)
def run_agent_task(self, workflow_id: str, user_prompt: str, github_token: str | None, task_execution_id: str | None = None, reasoning_effort: str | None = None):
    """Execute the agent engine inside an asyncio event loop.

    Each invocation creates a fresh event loop via asyncio.run(), initialises
    a Beanie/Motor DB connection, loads the Workflow document, and delegates
    to `run_agent()`.
    """
    worker = getattr(self.request, "hostname", None)
    try:
        asyncio.run(_execute(workflow_id, user_prompt, github_token, task_execution_id, worker, reasoning_effort))
    except Exception:
        # Best-effort: mark the workflow as failed if the task crashes
        try:
            asyncio.run(_mark_failed(workflow_id, task_execution_id))
        except Exception:
            logger.exception("Failed to mark workflow %s as failed", workflow_id)
        raise


async def _execute(workflow_id: str, user_prompt: str, github_token: str | None, task_execution_id: str | None = None, worker: str | None = None, reasoning_effort: str | None = None):
    """Async entry point — initialises DB and runs the agent.

    The engine/session factory is always disposed in the finally block so that
    the next asyncio.run() call (whether a subsequent task or _mark_failed)
    creates a fresh engine bound to the new event loop, avoiding the
    'Future attached to a different loop' RuntimeError.

    After run_agent() returns successfully this function also marks the
    TaskExecution as COMPLETED (with finished_at) so that Celery-level tests
    can verify completion without needing run_agent() to be unpatched.
    run_agent() may already do this internally; a duplicate COMPLETED write is
    harmless.
    """
    from datetime import UTC, datetime

    from app.core.agent_engine import run_agent
    from app.db import close_db, init_db, parse_doc_id
    from app.models.task_execution import TaskExecution, TaskStatus
    from app.models.workflow import Workflow

    try:
        await init_db()
        wf = await Workflow.get(parse_doc_id(workflow_id))
        if not wf:
            logger.error("Workflow %s not found", workflow_id)
            return

        # Set worker hostname on task execution
        if task_execution_id:
            te = await TaskExecution.get(parse_doc_id(task_execution_id))
            if te and worker:
                te.worker = worker
                await te.save()

        await run_agent(wf, user_prompt, github_token, task_execution_id, reasoning_effort)

        # Ensure the task is COMPLETED after a successful run.
        if task_execution_id:
            te = await TaskExecution.get(parse_doc_id(task_execution_id))
            if te and te.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.HALTED):
                te.status = TaskStatus.COMPLETED
                te.finished_at = datetime.now(UTC)
                await te.save()
    finally:
        await close_db()


async def _mark_failed(workflow_id: str, task_execution_id: str | None = None):
    """Mark a workflow as failed when the Celery task crashes unexpectedly.

    Always disposes the DB engine in the finally block so the next
    asyncio.run() call gets a fresh engine on the current event loop.
    """
    from datetime import UTC, datetime

    from app.core import event_bus
    from app.db import close_db, init_db, parse_doc_id
    from app.models.task_execution import TaskExecution, TaskStatus
    from app.models.workflow import Workflow, WorkflowStatus

    try:
        await init_db()
        wf = await Workflow.get(parse_doc_id(workflow_id))
        if wf and wf.status not in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.HALTED,
            WorkflowStatus.MAX_TURNS_REACHED,
            WorkflowStatus.ACTIVE,
            WorkflowStatus.INACTIVE,
        ):
            # Reset from RUNNING back to ACTIVE and publish the failure over SSE.
            # TaskExecution already records the failure detail — the workflow itself
            # should remain reusable (not stuck in FAILED/RUNNING).
            wf.status = WorkflowStatus.ACTIVE
            await wf.save()
            await event_bus.publish(
                workflow_id, "status", {"status": "failed", "current_turn": wf.current_turn}
            )

        if task_execution_id:
            te = await TaskExecution.get(parse_doc_id(task_execution_id))
            if te and te.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.HALTED):
                te.status = TaskStatus.FAILED
                te.finished_at = datetime.now(UTC)
                await te.save()
    finally:
        await close_db()
