from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.schemas.export_import import (
    AgentExportBundle,
    AgentImportBundle,
    ExportedAgent,
    ImportResult,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model=agent.model,
        mcp_server_ids=agent.mcp_server_ids,
        mcp_server_tags=agent.mcp_server_tags,
        tool_definitions=agent.tool_definitions,
        knowledge_source_ids=agent.knowledge_source_ids,
        knowledge_tags=agent.knowledge_tags,
        builtin_tools=agent.builtin_tools,
        custom_tool_ids=agent.custom_tool_ids,
        provider_id=agent.provider_id,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(body: AgentCreate, _user=Depends(get_current_user)):
    agent = Agent(**body.model_dump())
    await agent.insert()
    return _to_response(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(_user=Depends(get_current_user)):
    agents = await Agent.find_all().to_list()
    return [_to_response(a) for a in agents]


def _to_exported(agent: Agent) -> ExportedAgent:
    return ExportedAgent(
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model=agent.model,
        mcp_server_ids=agent.mcp_server_ids,
        mcp_server_tags=agent.mcp_server_tags,
        tool_definitions=agent.tool_definitions,
        knowledge_source_ids=agent.knowledge_source_ids,
        knowledge_tags=agent.knowledge_tags,
        builtin_tools=agent.builtin_tools,
        custom_tool_ids=agent.custom_tool_ids,
        provider_id=agent.provider_id,
    )


@router.get("/export", response_model=AgentExportBundle)
async def export_agents(_user=Depends(get_current_user)):
    agents = await Agent.find_all().to_list()
    return AgentExportBundle(items=[_to_exported(a) for a in agents])


@router.get("/{agent_id}/export", response_model=AgentExportBundle)
async def export_agent(agent_id: str, _user=Depends(get_current_user)):
    agent = await Agent.get(parse_doc_id(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentExportBundle(items=[_to_exported(agent)])


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_agents(body: AgentImportBundle, _user=Depends(get_current_user)):
    result = ImportResult()
    for item in body.items:
        try:
            agent = Agent(**item.model_dump())
            await agent.insert()
            result.ids.append(str(agent.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, _user=Depends(get_current_user)):
    agent = await Agent.get(parse_doc_id(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _to_response(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, body: AgentUpdate, _user=Depends(get_current_user)):
    agent = await Agent.get(parse_doc_id(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await agent.set(update_data)
    return _to_response(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, _user=Depends(get_current_user)):
    agent = await Agent.get(parse_doc_id(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await agent.delete()
