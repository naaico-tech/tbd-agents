from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.agent import Agent
from app.models.knowledge_source import KnowledgeSource, KnowledgeSourceType
from app.models.skill import Skill
from app.models.workflow import OutputFormat, Workflow
from app.schemas.export_import import (
    BundleImportResult,
    ExportedAgent,
    ExportedKnowledgeSource,
    ExportedSkill,
    ExportedWorkflow,
    FullExportBundle,
    ImportResult,
)

router = APIRouter(prefix="/api", tags=["export-import"])


@router.get("/export", response_model=FullExportBundle)
async def export_all(user=Depends(get_current_user)):
    """Export all skills, agents, user-owned workflows, and knowledge sources."""
    skills = await Skill.find_all().to_list()
    agents = await Agent.find_all().to_list()
    workflows = await Workflow.find(Workflow.github_user == user["login"]).to_list()
    knowledge_sources = await KnowledgeSource.find_all().to_list()

    return FullExportBundle(
        exported_at=datetime.now(UTC),
        skills=[
            ExportedSkill(
                name=s.name,
                description=s.description,
                instructions=s.instructions,
                tags=s.tags,
            )
            for s in skills
        ],
        agents=[
            ExportedAgent(
                name=a.name,
                description=a.description,
                system_prompt=a.system_prompt,
                model=a.model,
                mcp_server_ids=a.mcp_server_ids,
                mcp_server_tags=a.mcp_server_tags,
                tool_definitions=a.tool_definitions,
                knowledge_source_ids=a.knowledge_source_ids,
                knowledge_tags=a.knowledge_tags,
                builtin_tools=a.builtin_tools,
                custom_tool_ids=a.custom_tool_ids,
                provider_id=a.provider_id,
            )
            for a in agents
        ],
        workflows=[
            ExportedWorkflow(
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
            for wf in workflows
        ],
        knowledge_sources=[
            ExportedKnowledgeSource(
                name=ks.name,
                description=ks.description,
                source_type=ks.source_type,
                connection_config=ks.connection_config,
                tags=ks.tags,
            )
            for ks in knowledge_sources
        ],
    )


async def _import_skills(items: list[ExportedSkill]) -> ImportResult:
    result = ImportResult()
    for item in items:
        try:
            skill = Skill(**item.model_dump())
            await skill.insert()
            result.ids.append(str(skill.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


async def _import_agents(items: list[ExportedAgent]) -> ImportResult:
    result = ImportResult()
    for item in items:
        try:
            agent = Agent(**item.model_dump())
            await agent.insert()
            result.ids.append(str(agent.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


async def _import_workflows(items: list[ExportedWorkflow], github_user: str) -> ImportResult:
    result = ImportResult()
    for item in items:
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
                github_user=github_user,
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


async def _import_knowledge_sources(items: list[ExportedKnowledgeSource]) -> ImportResult:
    result = ImportResult()
    for item in items:
        try:
            source = KnowledgeSource(
                name=item.name,
                description=item.description,
                source_type=KnowledgeSourceType(item.source_type),
                connection_config=item.connection_config,
                tags=item.tags,
            )
            await source.insert()
            result.ids.append(str(source.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


@router.post("/import", response_model=BundleImportResult, status_code=201)
async def import_all(body: FullExportBundle, user=Depends(get_current_user)):
    """Import a full bundle (skills, agents, workflows, knowledge sources)."""
    return BundleImportResult(
        skills=await _import_skills(body.skills),
        agents=await _import_agents(body.agents),
        workflows=await _import_workflows(body.workflows, user["login"]),
        knowledge_sources=await _import_knowledge_sources(body.knowledge_sources),
    )
