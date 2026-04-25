"""Celery task fired by Celery Beat on each schedule tick.

This task:
1. Loads the ScheduledAgent from MongoDB.
2. Checks whether the schedule is still enabled and within its end_at window.
3. If expired → auto-disables the schedule and returns.
4. Creates a TaskExecution record.
5. Dispatches ``run_agent_task`` to the regular worker queue.
6. Updates ``last_run_at`` / ``next_run_at`` on the document.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.celery_app import celery
from app.db import init_db
from app.models.scheduled_agent import ScheduledAgent
from app.models.task_execution import TaskExecution, TaskStatus
from app.models.workflow import Workflow
from beanie.operators import In
from app.services import scheduler
from app.tasks.agent_task import run_agent_task

logger = logging.getLogger(__name__)


@celery.task(name="run_scheduled_agent", bind=True, max_retries=0)
def run_scheduled_agent(self, scheduled_agent_id: str):
    """Entry point called by Celery Beat on every interval tick."""
    try:
        asyncio.run(_execute(scheduled_agent_id))
    except Exception:
        logger.exception("Scheduled trigger failed for ScheduledAgent %s", scheduled_agent_id)
        raise


async def _execute(scheduled_agent_id: str) -> None:
    """Async execution body — loads DB, validates schedule, dispatches agent."""
    from beanie import PydanticObjectId

    await init_db()

    sa = await ScheduledAgent.get(PydanticObjectId(scheduled_agent_id))
    if not sa:
        logger.error("ScheduledAgent %s not found — skipping", scheduled_agent_id)
        return

    now = datetime.now(UTC)

    # ── Guard: disabled ──────────────────────────────────────────────────────
    if not sa.enabled:
        logger.info("ScheduledAgent %s is disabled — skipping", scheduled_agent_id)
        return

    # ── Guard: end_at exceeded ───────────────────────────────────────────────
    if sa.end_at and now >= sa.end_at:
        logger.info(
            "ScheduledAgent %s has passed its end_at (%s) — auto-disabling",
            scheduled_agent_id,
            sa.end_at,
        )
        scheduler.disable_schedule(sa)
        sa.enabled = False
        sa.updated_at = now
        await sa.save()
        return

    # -- Check for overlapping runs --
    active_te = await TaskExecution.find_one(
        TaskExecution.scheduled_agent_id == str(sa.id),
        In(TaskExecution.status, [TaskStatus.PENDING, TaskStatus.RUNNING])
    )
    if active_te:
        logger.warning(
            "ScheduledAgent %s: previous run %s is still active (%s) — skipping this tick to avoid overlap",
            scheduled_agent_id, active_te.id, active_te.status
        )
        return


    # ── Validate the target workflow still exists ────────────────────────────
    wf = await Workflow.get(PydanticObjectId(sa.workflow_id))
    if not wf:
        logger.error(
            "ScheduledAgent %s references missing Workflow %s — skipping",
            scheduled_agent_id,
            sa.workflow_id,
        )
        return


    # -- Create a TaskExecution record --
    te = TaskExecution(
        workflow_id=sa.workflow_id,
        prompt=sa.prompt,
        status=TaskStatus.PENDING,
        scheduled_agent_id=str(sa.id),
    )
    await te.insert()

    # ── Dispatch to the regular worker queue ─────────────────────────────────
    run_agent_task.delay(
        sa.workflow_id,
        sa.prompt,
        None,                  # no per-request GitHub token for scheduled runs
        str(te.id),
        wf.reasoning_effort,
    )
    logger.info(
        "ScheduledAgent %s dispatched run_agent_task (workflow=%s, te=%s)",
        scheduled_agent_id,
        sa.workflow_id,
        te.id,
    )

    # ── Update run timestamps ────────────────────────────────────────────────
    delta = _to_timedelta(sa.interval_value, sa.interval_unit)
    sa.last_run_at = now
    sa.next_run_at = now + delta
    sa.updated_at = now
    await sa.save()


def _to_timedelta(value: int, unit: str) -> timedelta:
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    if unit == "days":
        return timedelta(days=value)
    raise ValueError(f"Unknown interval unit: {unit!r}")
