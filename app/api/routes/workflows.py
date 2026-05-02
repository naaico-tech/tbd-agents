import json as _json

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import extract_optional_token, get_current_user
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
from app.observability import sse_connections_active
from app.schemas.export_import import (
    ExportedWorkflow,
    ImportResult,
    WorkflowExportBundle,
    WorkflowImportBundle,
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


async def _to_response(wf: Workflow) -> WorkflowResponse:
    # Count tasks and get last task info
    tasks = await TaskExecution.find(
        TaskExecution.workflow_id == str(wf.id)
    ).sort("-created_at").limit(1).to_list()
    task_count_val = await TaskExecution.find(
        TaskExecution.workflow_id == str(wf.id)
    ).count()
    last_task = tasks[0] if tasks else None
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
        skill_tags=wf.skill_tags,
        status=wf.status,
        output_format=wf.output_format,
        infinite_session=wf.infinite_session,
        caveman=wf.caveman,
        bypass_memory=wf.bypass_memory,
        auto_memory=wf.auto_memory,
        tsv_tool_results=wf.tsv_tool_results,
        reasoning_effort=wf.reasoning_effort,
        guardrail_ids=wf.guardrail_ids,
        guardrail_tags=wf.guardrail_tags,
        repo_url=wf.repo_url,
        repo_branch=wf.repo_branch,
        repo_token_name=wf.repo_token_name,
        credential_overrides=wf.credential_overrides,
        usage=_usage_response(wf),
        logs=[LogEntryResponse(**le.model_dump()) for le in wf.logs],
        messages=[MessageResponse(**m.model_dump()) for m in wf.messages],
        task_count=task_count_val,
        last_task_status=last_task.status if last_task else None,
        last_task_at=last_task.created_at if last_task else None,
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
        skill_tags=body.skill_tags,
        output_format=OutputFormat(body.output_format),
        infinite_session=body.infinite_session,
        caveman=body.caveman,
        bypass_memory=body.bypass_memory,
        auto_memory=body.auto_memory,
        tsv_tool_results=body.tsv_tool_results,
        reasoning_effort=body.reasoning_effort,
        guardrail_ids=body.guardrail_ids,
        guardrail_tags=body.guardrail_tags,
        repo_url=body.repo_url,
        repo_branch=body.repo_branch,
        repo_token_name=body.repo_token_name,
        credential_overrides=body.credential_overrides,
    )
    await wf.insert()
    return await _to_response(wf)


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
    if wf.status != WorkflowStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow is {wf.status}, cannot send prompt",
        )

    # Reset logs/messages for a new run
    wf.logs = []
    wf.messages = []
    wf.current_turn = 0
    await wf.save()

    token = extract_optional_token(authorization)

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
        caveman=wf.caveman,
        tsv_tool_results=wf.tsv_tool_results,
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
    if wf.status != WorkflowStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Workflow is {wf.status}, not active")
    # Check if there is actually a running task for this workflow
    running_task = await TaskExecution.find_one(
        TaskExecution.workflow_id == str(wf.id),
        TaskExecution.status == "running",
    )
    if not running_task:
        raise HTTPException(status_code=400, detail="No running task to halt")
    await event_bus.set_halt(str(wf.id))
    return {"detail": "Halt signal sent"}


@router.get("/{workflow_id}/stream")
async def stream_workflow(
    workflow_id: str,
    request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
):
    """SSE endpoint — streams real-time log/message/usage/status events.

    Supports reconnection via the ``Last-Event-ID`` header: on reconnect the
    server replays any events the client missed before switching to live
    streaming.
    """
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Parse Last-Event-ID to an integer (ignore invalid values)
    resume_id: int | None = None
    if last_event_id is not None:
        try:
            resume_id = int(last_event_id)
        except (ValueError, TypeError):
            pass

    async def event_generator():
        sse_connections_active.inc()
        try:
            async for payload in event_bus.subscribe(workflow_id, last_event_id=resume_id):
                if await request.is_disconnected():
                    break
                if payload is None:
                    yield ": keepalive\n\n"
                else:
                    # Extract event ID for the SSE id: field
                    try:
                        evt = _json.loads(payload)
                        event_id = evt.get("id")
                        if event_id is not None:
                            yield f"id: {event_id}\ndata: {payload}\n\n"
                        else:
                            yield f"data: {payload}\n\n"
                    except Exception:
                        yield f"data: {payload}\n\n"
        except Exception:
            pass
        finally:
            sse_connections_active.dec()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _to_exported_wf(wf: Workflow) -> ExportedWorkflow:
    return ExportedWorkflow(
        title=wf.title,
        agent_id=wf.agent_id,
        model=wf.model,
        max_turns=wf.max_turns,
        skill_ids=wf.skill_ids,
        skill_tags=wf.skill_tags,
        output_format=wf.output_format,
        infinite_session=wf.infinite_session,
        caveman=wf.caveman,
        bypass_memory=wf.bypass_memory,
        auto_memory=wf.auto_memory,
        tsv_tool_results=wf.tsv_tool_results,
        reasoning_effort=wf.reasoning_effort,
        guardrail_ids=wf.guardrail_ids,
        guardrail_tags=wf.guardrail_tags,
        repo_url=wf.repo_url,
        repo_branch=wf.repo_branch,
        repo_token_name=wf.repo_token_name,
    )


@router.get("/export", response_model=WorkflowExportBundle)
async def export_workflows(user=Depends(get_current_user)):
    workflows = await Workflow.find(Workflow.github_user == user["login"]).to_list()
    return WorkflowExportBundle(items=[_to_exported_wf(wf) for wf in workflows])


@router.get("/{workflow_id}/export", response_model=WorkflowExportBundle)
async def export_workflow(workflow_id: str, user=Depends(get_current_user)):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    return WorkflowExportBundle(items=[_to_exported_wf(wf)])


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_workflows(body: WorkflowImportBundle, user=Depends(get_current_user)):
    result = ImportResult()
    for item in body.items:
        try:
            agent = await Agent.get(PydanticObjectId(item.agent_id))
            if not agent:
                result.errors.append(
                    f"{item.title or 'untitled'}: agent_id {item.agent_id!r} not found"
                )
                continue
            wf = Workflow(
                title=item.title,
                agent_id=item.agent_id,
                github_user=user["login"],
                model=item.model,
                max_turns=item.max_turns,
                skill_ids=item.skill_ids,
                skill_tags=item.skill_tags,
                output_format=OutputFormat(item.output_format),
                infinite_session=item.infinite_session,
                caveman=item.caveman,
                bypass_memory=item.bypass_memory,
                auto_memory=item.auto_memory,
                tsv_tool_results=item.tsv_tool_results,
                reasoning_effort=item.reasoning_effort,
                guardrail_ids=item.guardrail_ids,
                guardrail_tags=item.guardrail_tags,
                repo_url=item.repo_url,
                repo_branch=item.repo_branch,
                repo_token_name=item.repo_token_name,
            )
            await wf.insert()
            result.ids.append(str(wf.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.title or 'untitled'}: {exc}")
    return result


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, user=Depends(get_current_user)):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    return await _to_response(wf)


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
    if "status" in updates:
        if updates["status"] not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="status must be 'active' or 'inactive'")
        updates["status"] = WorkflowStatus(updates["status"])
    for k, v in updates.items():
        setattr(wf, k, v)
    from datetime import UTC, datetime
    wf.updated_at = datetime.now(UTC)
    await wf.save()
    return await _to_response(wf)


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
    return [await _to_response(wf) for wf in workflows]


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
    return await _to_response(wf)


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
    return await _to_response(wf)
