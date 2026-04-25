"""REST API routes for Scheduled Agent CRUD and lifecycle management."""

import logging
from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.scheduled_agent import ScheduledAgent
from app.models.workflow import Workflow
from app.schemas.scheduled_agent import (
    ScheduledAgentCreate,
    ScheduledAgentResponse,
    ScheduledAgentUpdate,
)
from app.services import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduled-agents", tags=["scheduled-agents"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_response(sa: ScheduledAgent) -> ScheduledAgentResponse:
    return ScheduledAgentResponse(
        id=str(sa.id),
        name=sa.name,
        workflow_id=sa.workflow_id,
        prompt=sa.prompt,
        interval_value=sa.interval_value,
        interval_unit=sa.interval_unit,
        start_at=sa.start_at,
        end_at=sa.end_at,
        enabled=sa.enabled,
        last_run_at=sa.last_run_at,
        next_run_at=sa.next_run_at,
        created_at=sa.created_at,
        updated_at=sa.updated_at,
    )


async def _get_owned(sa_id: str, user: dict) -> ScheduledAgent:
    """Load a ScheduledAgent and verify it belongs to the authenticated user."""
    sa = await ScheduledAgent.get(PydanticObjectId(sa_id))
    if not sa:
        raise HTTPException(status_code=404, detail="Scheduled agent not found")
    wf = await Workflow.get(PydanticObjectId(sa.workflow_id))
    if not wf or wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your scheduled agent")
    return sa


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=ScheduledAgentResponse, status_code=201)
async def create_scheduled_agent(
    body: ScheduledAgentCreate,
    user=Depends(get_current_user),
):
    """Create and immediately register a new scheduled agent."""
    # Verify ownership of the referenced workflow
    wf = await Workflow.get(PydanticObjectId(body.workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")

    sa = ScheduledAgent(**body.model_dump())
    await sa.insert()

    try:
        key = scheduler.create_schedule(sa)
        sa.redbeat_key = key
        sa.updated_at = datetime.now(UTC)
        await sa.save()
    except Exception:
        # Don't leave an orphaned DB record if Beat registration fails
        await sa.delete()
        logger.exception("Failed to register RedBeat schedule for ScheduledAgent")
        raise HTTPException(status_code=500, detail="Failed to register schedule with Beat scheduler")

    return _to_response(sa)


@router.get("", response_model=list[ScheduledAgentResponse])
async def list_scheduled_agents(user=Depends(get_current_user)):
    """List all scheduled agents that belong to the authenticated user."""
    user_workflows = await Workflow.find(Workflow.github_user == user["login"]).to_list()
    wf_ids = {str(wf.id) for wf in user_workflows}
    all_sas = await ScheduledAgent.find_all().sort("-created_at").to_list()
    return [_to_response(sa) for sa in all_sas if sa.workflow_id in wf_ids]


@router.get("/{sa_id}", response_model=ScheduledAgentResponse)
async def get_scheduled_agent(sa_id: str, user=Depends(get_current_user)):
    """Get a single scheduled agent by ID."""
    sa = await _get_owned(sa_id, user)
    return _to_response(sa)


@router.patch("/{sa_id}", response_model=ScheduledAgentResponse)
async def update_scheduled_agent(
    sa_id: str,
    body: ScheduledAgentUpdate,
    user=Depends(get_current_user),
):
    """Update a scheduled agent's configuration.

    If any timing or interval field changes, the RedBeat entry is rebuilt so
    the new cadence takes effect immediately.
    """
    sa = await _get_owned(sa_id, user)

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        return _to_response(sa)

    schedule_fields = {"interval_value", "interval_unit", "start_at", "end_at"}
    needs_reschedule = bool(update_data.keys() & schedule_fields)

    update_data["updated_at"] = datetime.now(UTC)
    await sa.set(update_data)

    if needs_reschedule and sa.enabled:
        try:
            key = scheduler.update_schedule(sa)
            await sa.set({"redbeat_key": key, "updated_at": datetime.now(UTC)})
        except Exception:
            logger.exception("Failed to update RedBeat schedule for ScheduledAgent %s", sa_id)
            raise HTTPException(status_code=500, detail="Failed to update schedule with Beat scheduler")

    return _to_response(sa)


@router.patch("/{sa_id}/enable", response_model=ScheduledAgentResponse)
async def enable_scheduled_agent(sa_id: str, user=Depends(get_current_user)):
    """Re-enable a disabled scheduled agent."""
    sa = await _get_owned(sa_id, user)
    if sa.enabled:
        return _to_response(sa)

    try:
        key = scheduler.enable_schedule(sa)
    except Exception:
        logger.exception("Failed to enable RedBeat schedule for ScheduledAgent %s", sa_id)
        raise HTTPException(status_code=500, detail="Failed to enable schedule with Beat scheduler")

    now = datetime.now(UTC)
    await sa.set({"enabled": True, "redbeat_key": key, "updated_at": now})
    return _to_response(sa)


@router.patch("/{sa_id}/disable", response_model=ScheduledAgentResponse)
async def disable_scheduled_agent(sa_id: str, user=Depends(get_current_user)):
    """Disable an active scheduled agent without deleting it."""
    sa = await _get_owned(sa_id, user)
    if not sa.enabled:
        return _to_response(sa)

    try:
        scheduler.disable_schedule(sa)
    except Exception:
        logger.exception("Failed to disable RedBeat schedule for ScheduledAgent %s", sa_id)
        raise HTTPException(status_code=500, detail="Failed to disable schedule with Beat scheduler")

    await sa.set({"enabled": False, "updated_at": datetime.now(UTC)})
    return _to_response(sa)


@router.delete("/{sa_id}", status_code=204)
async def delete_scheduled_agent(sa_id: str, user=Depends(get_current_user)):
    """Permanently delete a scheduled agent and remove its Beat entry."""
    sa = await _get_owned(sa_id, user)
    scheduler.delete_schedule(sa)
    await sa.delete()
