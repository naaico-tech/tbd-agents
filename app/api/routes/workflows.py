import asyncio

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import extract_token, get_current_user
from app.config import settings
from app.core.agent_engine import run_agent
from app.models.agent import Agent
from app.models.skill import Skill
from app.models.workflow import OutputFormat, Workflow, WorkflowStatus
from app.schemas.workflow import (
    LogEntryResponse,
    MessageResponse,
    PromptRequest,
    PromptResponse,
    WorkflowCreate,
    WorkflowResponse,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _to_response(wf: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=str(wf.id),
        agent_id=wf.agent_id,
        github_user=wf.github_user,
        model=wf.model,
        max_turns=wf.max_turns,
        current_turn=wf.current_turn,
        session_id=wf.session_id,
        skill_ids=wf.skill_ids,
        status=wf.status,
        output_format=wf.output_format,
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
        agent_id=str(agent.id),
        github_user=user["login"],
        model=model,
        max_turns=max_turns,
        skill_ids=body.skill_ids,
        output_format=OutputFormat(body.output_format),
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
    if wf.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.COMPLETED):
        raise HTTPException(
            status_code=400,
            detail=f"Workflow is {wf.status}, cannot send prompt",
        )

    # Reset for a new run if re-prompting a completed workflow
    if wf.status == WorkflowStatus.COMPLETED:
        wf.status = WorkflowStatus.ACTIVE

    token = extract_token(authorization)

    # Launch the agent loop in the background
    asyncio.get_running_loop().create_task(run_agent(wf, body.prompt, token))

    return PromptResponse(
        workflow_id=str(wf.id),
        status="running",
        current_turn=wf.current_turn,
        max_turns=wf.max_turns,
        response=None,
        output_format=wf.output_format,
        logs=[LogEntryResponse(**le.model_dump()) for le in wf.logs],
        messages=[MessageResponse(**m.model_dump()) for m in wf.messages],
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, user=Depends(get_current_user)):
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your workflow")
    return _to_response(wf)


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
