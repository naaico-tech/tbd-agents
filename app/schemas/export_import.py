from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ExportedSkill(BaseModel):
    name: str
    description: str = ""
    instructions: str
    tags: list[str] = []


class ExportedAgent(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful assistant."
    model: str | None = None
    mcp_server_ids: list[str] = []
    mcp_server_tags: list[str] = []
    tool_definitions: list[dict] = []
    knowledge_source_ids: list[str] = []
    knowledge_tags: list[str] = []
    builtin_tools: list[str] = []
    custom_tool_ids: list[str] = []
    provider_id: str | None = None


class ExportedWorkflow(BaseModel):
    title: str | None = None
    agent_id: str
    model: str
    max_turns: int = 5
    skill_ids: list[str] = []
    skill_tags: list[str] = []
    output_format: str = "json"
    infinite_session: bool = True
    caveman: bool = False
    bypass_memory: bool = False
    auto_memory: bool = False
    tsv_tool_results: bool = False
    reasoning_effort: str | None = None
    guardrail_ids: list[str] = []
    guardrail_tags: list[str] = []
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_token_name: str | None = None
    repository_ids: list[str] = []
    repository_tags: list[str] = []


class ExportedKnowledgeSource(BaseModel):
    name: str
    description: str = ""
    source_type: str
    connection_config: dict[str, Any] = {}
    tags: list[str] = []


class ExportedCodeRepository(BaseModel):
    name: str
    description: str = ""
    repo_url: str
    default_branch: str = "main"
    token_name: str | None = None
    tags: list[str] = []
    indexing: dict[str, Any] = {}


# ── Per-resource bundles ─────────────────────────────────────────────────────


class SkillExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_type: str = "skill"
    items: list[ExportedSkill]


class AgentExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_type: str = "agent"
    items: list[ExportedAgent]


class WorkflowExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_type: str = "workflow"
    items: list[ExportedWorkflow]


class KnowledgeSourceExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_type: str = "knowledge_source"
    items: list[ExportedKnowledgeSource]


class CodeRepositoryExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_type: str = "code_repository"
    items: list[ExportedCodeRepository]


# ── Full bundle (all resources) ───────────────────────────────────────────────


class FullExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_type: str = "bundle"
    skills: list[ExportedSkill] = []
    agents: list[ExportedAgent] = []
    workflows: list[ExportedWorkflow] = []
    knowledge_sources: list[ExportedKnowledgeSource] = []


# ── Import schemas ────────────────────────────────────────────────────────────


class ImportResult(BaseModel):
    created: int = 0
    errors: list[str] = []
    ids: list[str] = []


class SkillImportBundle(BaseModel):
    items: list[ExportedSkill]


class AgentImportBundle(BaseModel):
    items: list[ExportedAgent]


class WorkflowImportBundle(BaseModel):
    items: list[ExportedWorkflow]


class KnowledgeSourceImportBundle(BaseModel):
    items: list[ExportedKnowledgeSource]


class CodeRepositoryImportBundle(BaseModel):
    items: list[ExportedCodeRepository]


class BundleImportResult(BaseModel):
    skills: ImportResult = Field(default_factory=ImportResult)
    agents: ImportResult = Field(default_factory=ImportResult)
    workflows: ImportResult = Field(default_factory=ImportResult)
    knowledge_sources: ImportResult = Field(default_factory=ImportResult)
