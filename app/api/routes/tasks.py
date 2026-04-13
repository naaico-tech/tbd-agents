from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.agent import Agent
from app.models.task_execution import TaskExecution
from app.models.workflow import Workflow
from app.schemas.task_execution import (
    TaskExecutionResponse,
    TaskExecutionSummary,
    TaskProgressResponse,
    TodoItemResponse,
)
from app.schemas.workflow import LogEntryResponse, MessageResponse, UsageStatsResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _elapsed(te: TaskExecution) -> float | None:
    from datetime import UTC, datetime, timezone

    def _make_aware(dt):
        """Ensure a datetime is timezone-aware (UTC)."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    started = _make_aware(te.started_at)
    finished = _make_aware(te.finished_at)
    if started and finished:
        return (finished - started).total_seconds()
    if started:
        return (datetime.now(UTC) - started).total_seconds()
    return None


def _usage_response(te: TaskExecution) -> UsageStatsResponse | None:
    if not te.usage:
        return None
    return UsageStatsResponse(**te.usage.model_dump())


async def _to_summary(te: TaskExecution) -> TaskExecutionSummary:
    wf = await Workflow.get(PydanticObjectId(te.workflow_id))
    workflow_title = wf.title if wf else None
    agent_name = None
    if wf:
        agent = await Agent.get(PydanticObjectId(wf.agent_id))
        agent_name = agent.name if agent else None
    return TaskExecutionSummary(
        id=str(te.id),
        workflow_id=te.workflow_id,
        workflow_title=workflow_title,
        agent_name=agent_name,
        prompt=te.prompt,
        status=te.status,
        worker=te.worker,
        model=te.model,
        reasoning_effort=te.reasoning_effort,
        tool_calls=te.tool_calls,
        started_at=te.started_at,
        finished_at=te.finished_at,
        elapsed_seconds=_elapsed(te),
        created_at=te.created_at,
    )


def _progress_response(te: TaskExecution) -> TaskProgressResponse | None:
    if not te.progress:
        return None
    return TaskProgressResponse(
        todos=[TodoItemResponse(id=t.id, title=t.title, status=t.status) for t in te.progress.todos],
        current_step=te.progress.current_step,
        percent_complete=te.progress.percent_complete,
    )


async def _to_response(te: TaskExecution) -> TaskExecutionResponse:
    wf = await Workflow.get(PydanticObjectId(te.workflow_id))
    workflow_title = wf.title if wf else None
    agent_name = None
    if wf:
        agent = await Agent.get(PydanticObjectId(wf.agent_id))
        agent_name = agent.name if agent else None
    return TaskExecutionResponse(
        id=str(te.id),
        workflow_id=te.workflow_id,
        workflow_title=workflow_title,
        agent_name=agent_name,
        prompt=te.prompt,
        status=te.status,
        celery_task_id=te.celery_task_id,
        worker=te.worker,
        model=te.model,
        reasoning_effort=te.reasoning_effort,
        tool_calls=te.tool_calls,
        response=te.response,
        progress=_progress_response(te),
        logs=[LogEntryResponse(**le.model_dump()) for le in te.logs],
        messages=[MessageResponse(**m.model_dump()) for m in te.messages],
        usage=_usage_response(te),
        started_at=te.started_at,
        finished_at=te.finished_at,
        elapsed_seconds=_elapsed(te),
        created_at=te.created_at,
    )


@router.get("", response_model=list[TaskExecutionSummary])
async def list_tasks(user=Depends(get_current_user)):
    """List all task executions for the current user's workflows."""
    user_workflows = await Workflow.find(Workflow.github_user == user["login"]).to_list()
    wf_ids = {str(wf.id) for wf in user_workflows}
    all_tasks = await TaskExecution.find_all().sort("-created_at").to_list()
    user_tasks = [t for t in all_tasks if t.workflow_id in wf_ids]
    return [await _to_summary(t) for t in user_tasks]


@router.get("/{task_id}", response_model=TaskExecutionResponse)
async def get_task(task_id: str, user=Depends(get_current_user)):
    """Get a single task execution with full logs and messages."""
    te = await TaskExecution.get(PydanticObjectId(task_id))
    if not te:
        raise HTTPException(status_code=404, detail="Task execution not found")
    # Verify ownership
    wf = await Workflow.get(PydanticObjectId(te.workflow_id))
    if not wf or wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your task")
    return await _to_response(te)


@router.get("/{task_id}/progress", response_model=TaskProgressResponse)
async def get_task_progress(task_id: str, user=Depends(get_current_user)):
    """Get the current TODO progress for a task execution."""
    te = await TaskExecution.get(PydanticObjectId(task_id))
    if not te:
        raise HTTPException(status_code=404, detail="Task execution not found")
    wf = await Workflow.get(PydanticObjectId(te.workflow_id))
    if not wf or wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your task")
    if not te.progress:
        return TaskProgressResponse()
    return TaskProgressResponse(
        todos=[TodoItemResponse(id=t.id, title=t.title, status=t.status) for t in te.progress.todos],
        current_step=te.progress.current_step,
        percent_complete=te.progress.percent_complete,
    )


@router.get("/workflow/{workflow_id}", response_model=list[TaskExecutionSummary])
async def list_workflow_tasks(workflow_id: str, user=Depends(get_current_user)):
    """List all task executions for a specific workflow."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    tasks = await TaskExecution.find(
        TaskExecution.workflow_id == workflow_id
    ).sort("-created_at").to_list()
    return [await _to_summary(t) for t in tasks]
