from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import extract_token, get_current_user
from app.config import settings
from app.core import event_bus
from app.core.guardrails import enforce_guardrails
from app.models.agent import Agent
from app.models.skill import Skill
from app.models.task_execution import TaskExecution
from app.models.workflow import (
    OutputFormat,
    Workflow,
    WorkflowStatus,
)
from app.schemas.workflow import (
    LogEntryResponse,
    MessageResponse,
    PromptRequest,
    PromptResponse,
    UsageStatsResponse,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.tasks.agent_task import run_agent_task

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _usage_response(wf: Workflow) -> UsageStatsResponse | None:
    if not wf.usage:
        return None
    return UsageStatsResponse(**wf.usage.model_dump())


def _to_response(wf: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=str(wf.id),
        title=wf.title,
        agent_id=wf.agent_id,
        github_user=wf.github_user,
        model=wf.model,
        max_turns=wf.max_turns,
        current_turn=wf.current_turn,
        session_id=wf.session_id,
        skill_ids=wf.skill_ids,
        status=wf.status,
        output_format=wf.output_format,
        infinite_session=wf.infinite_session,
        reasoning_effort=wf.reasoning_effort,
        guardrail_ids=wf.guardrail_ids,
        guardrail_tags=wf.guardrail_tags,
        repo_url=wf.repo_url,
        repo_branch=wf.repo_branch,
        repo_token_name=wf.repo_token_name,
        knowledge_base_ids=wf.knowledge_base_ids,
        usage=_usage_response(wf),
        logs=[LogEntryResponse(**le.model_dump()) for le in wf.logs],
        messages=[MessageResponse(**m.model_dump()) for m in wf.messages],
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(body: WorkflowCreate, user=Depends(get_current_user)):
    agent = await Agent.get(PydanticObjectId(body.agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    model = body.model or agent.model or settings.default_model
    max_turns = body.max_turns if body.max_turns is not None else settings.default_max_turns

    if body.output_format not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail="output_format must be 'json' or 'markdown'")

    wf = Workflow(
        title=body.title,
        agent_id=str(agent.id),
        github_user=user["login"],
        model=model,
        max_turns=max_turns,
        skill_ids=body.skill_ids,
        output_format=OutputFormat(body.output_format),
        infinite_session=body.infinite_session,
        reasoning_effort=body.reasoning_effort,
        guardrail_ids=body.guardrail_ids,
        guardrail_tags=body.guardrail_tags,
        repo_url=body.repo_url,
        repo_branch=body.repo_branch,
        repo_token_name=body.repo_token_name,
        knowledge_base_ids=body.knowledge_base_ids,
    )
    await wf.insert()
    return _to_response(wf)


@router.post("/{workflow_id}/prompt", response_model=PromptResponse, status_code=201)
async def send_prompt(
    workflow_id: str,
    body: PromptRequest,
    user=Depends(get_current_user),
    authorization: str | None = Header(None),
):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    if wf.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.HALTED, WorkflowStatus.MAX_TURNS_REACHED):
        raise HTTPException(
            status_code=400,
            detail=f"Workflow is {wf.status}, cannot send prompt",
        )

    # Reset for a new run if re-prompting a finished or stale workflow
    if wf.status in (WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.HALTED, WorkflowStatus.MAX_TURNS_REACHED):
        wf.status = WorkflowStatus.ACTIVE
        wf.logs = []
        wf.messages = []
        wf.current_turn = 0
        await wf.save()

    token = extract_token(authorization)

    # ── Guardrail enforcement ─────────────────────────────────────────────────
    effective_prompt = await enforce_guardrails(wf, body.prompt, body.request)

    # Resolve reasoning effort: prompt-time override > workflow default
    reasoning_effort = body.reasoning_effort or wf.reasoning_effort

    # Create a task execution record
    task_exec = TaskExecution(
        workflow_id=str(wf.id),
        prompt=effective_prompt,
        model=wf.model,
        reasoning_effort=reasoning_effort,
    )
    await task_exec.insert()

    # Dispatch to a Celery worker for scalable background execution
    result = run_agent_task.delay(
        str(wf.id), effective_prompt, token, str(task_exec.id), reasoning_effort
    )

    # Store the Celery task ID
    task_exec.celery_task_id = result.id
    await task_exec.save()

    return PromptResponse(
        workflow_id=str(wf.id),
        status="running",
        current_turn=wf.current_turn,
        max_turns=wf.max_turns,
        response=None,
        output_format=wf.output_format,
        infinite_session=wf.infinite_session,
        usage=_usage_response(wf),
        logs=[LogEntryResponse(**le.model_dump()) for le in wf.logs],
        messages=[MessageResponse(**m.model_dump()) for m in wf.messages],
    )


@router.post("/{workflow_id}/halt", status_code=202)
async def halt_workflow(workflow_id: str, user=Depends(get_current_user)):
    """Signal a running workflow to halt. The worker will abort the SDK session."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    if wf.status != WorkflowStatus.RUNNING:
        raise HTTPException(status_code=400, detail=f"Workflow is {wf.status}, not running")
    await event_bus.set_halt(str(wf.id))
    return {"detail": "Halt signal sent"}


@router.get("/{workflow_id}/stream")
async def stream_workflow(workflow_id: str, request: Request):
    """SSE endpoint — streams real-time log/message/usage/status events."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    async def event_generator():
        try:
            async for payload in event_bus.subscribe(workflow_id):
                if await request.is_disconnected():
                    break
                if payload is None:
                    yield ": keepalive\n\n"
                else:
                    yield f"data: {payload}\n\n"
        except Exception:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, user=Depends(get_current_user)):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    return _to_response(wf)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str, body: WorkflowUpdate, user=Depends(get_current_user)
):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")

    updates = body.model_dump(exclude_unset=True)
    if "agent_id" in updates:
        agent = await Agent.get(PydanticObjectId(updates["agent_id"]))
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        updates["agent_id"] = str(agent.id)
    if "output_format" in updates and updates["output_format"] not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail="output_format must be 'json' or 'markdown'")
    if "output_format" in updates:
        updates["output_format"] = OutputFormat(updates["output_format"])
    for k, v in updates.items():
        setattr(wf, k, v)
    from datetime import UTC, datetime
    wf.updated_at = datetime.now(UTC)
    await wf.save()
    return _to_response(wf)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, user=Depends(get_current_user)):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    await wf.delete()
    return None


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(user=Depends(get_current_user)):
    workflows = await Workflow.find(Workflow.github_user == user["login"]).to_list()
    return [_to_response(wf) for wf in workflows]


@router.post("/{workflow_id}/skills/{skill_id}", response_model=WorkflowResponse)
async def install_skill(
    workflow_id: str, skill_id: str, user=Depends(get_current_user)
):
    """Install a skill into a workflow."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    skill = await Skill.get(PydanticObjectId(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill_id in wf.skill_ids:
        raise HTTPException(status_code=409, detail="Skill already installed")
    wf.skill_ids.append(skill_id)
    await wf.save()
    return _to_response(wf)


@router.delete("/{workflow_id}/skills/{skill_id}", response_model=WorkflowResponse)
async def remove_skill(
    workflow_id: str, skill_id: str, user=Depends(get_current_user)
):
    """Remove a skill from a workflow."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    if skill_id not in wf.skill_ids:
        raise HTTPException(status_code=404, detail="Skill not installed in this workflow")
    wf.skill_ids.remove(skill_id)
    await wf.save()
    return _to_response(wf)
