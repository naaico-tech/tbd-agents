"""Tests for Pydantic models (validation, defaults, enums)."""


import pytest
from pydantic import ValidationError

# ── Agent ────────────────────────────────────────────────────────────────────
# Beanie Document classes require init_beanie to be called before instantiation.
# We use model_construct() to test field defaults without hitting MongoDB.
from app.models.agent import Agent
from app.models.guardrail import (
    Guardrail,
    GuardrailType,
    PromptGuardrailConfig,
    RequestGuardrailConfig,
)
from app.models.mcp_server import McpServer, McpServerStatus, TransportType
from app.models.skill import Skill
from app.models.task_execution import (
    TaskExecution,
    TaskProgress,
    TaskStatus,
    TodoItem,
    TodoItemStatus,
)
from app.models.token import Token
from app.models.workflow import (
    LogEntry,
    Message,
    OutputFormat,
    UsageStats,
    Workflow,
    WorkflowStatus,
)


class TestAgentModel:
    def test_agent_defaults(self):
        a = Agent.model_construct(name="test")
        assert a.name == "test"
        assert Agent.model_fields["description"].default == ""
        assert Agent.model_fields["system_prompt"].default == "You are a helpful assistant."

    def test_agent_custom_values(self):
        a = Agent.model_construct(
            name="custom",
            description="desc",
            system_prompt="Be brief.",
            model="gpt-4.1",
            mcp_server_ids=["s1", "s2"],
            mcp_server_tags=["data", "messaging"],
        )
        assert a.model == "gpt-4.1"
        assert len(a.mcp_server_ids) == 2
        assert a.mcp_server_tags == ["data", "messaging"]


# ── Skill ────────────────────────────────────────────────────────────────────


class TestSkillModel:
    def test_skill_creation(self):
        s = Skill.model_construct(name="coder", instructions="Write clean code.")
        assert s.name == "coder"
        assert s.instructions == "Write clean code."

    def test_skill_with_tags(self):
        s = Skill.model_construct(name="analyst", instructions="Analyze.", tags=["data", "ml"])
        assert s.tags == ["data", "ml"]


# ── Guardrail ────────────────────────────────────────────────────────────────


class TestGuardrailModel:
    def test_prompt_guardrail_requires_config(self):
        with pytest.raises(ValidationError, match="prompt_config is required"):
            Guardrail.model_validate({
                "name": "test",
                "guardrail_type": GuardrailType.PROMPT,
                "prompt_config": None,
            })

    def test_request_guardrail_requires_config(self):
        with pytest.raises(ValidationError, match="request_config is required"):
            Guardrail.model_validate({
                "name": "test",
                "guardrail_type": GuardrailType.REQUEST,
                "request_config": None,
            })

    def test_valid_prompt_guardrail(self):
        g = Guardrail.model_construct(
            name="length-check",
            guardrail_type=GuardrailType.PROMPT,
            prompt_config=PromptGuardrailConfig(min_length=5, max_length=1000),
        )
        assert g.guardrail_type == GuardrailType.PROMPT
        assert g.prompt_config.min_length == 5

    def test_valid_request_guardrail(self):
        g = Guardrail.model_construct(
            name="schema-check",
            guardrail_type=GuardrailType.REQUEST,
            request_config=RequestGuardrailConfig(
                json_schema={"type": "object", "required": ["query"]}
            ),
        )
        assert g.request_config.json_schema["required"] == ["query"]

    def test_guardrail_tags_and_enabled(self):
        g = Guardrail.model_construct(
            name="tagged",
            guardrail_type=GuardrailType.PROMPT,
            prompt_config=PromptGuardrailConfig(),
            tags=["safety", "production"],
            enabled=False,
        )
        assert g.tags == ["safety", "production"]
        assert g.enabled is False


# ── McpServer ────────────────────────────────────────────────────────────────


class TestMcpServerModel:
    def test_stdio_server(self):
        s = McpServer.model_construct(
            name="notion",
            transport_type=TransportType.STDIO,
            connection_config={"command": "npx", "args": ["-y", "notion-mcp"]},
            status=McpServerStatus.REGISTERED,
        )
        assert s.transport_type == TransportType.STDIO
        assert s.status == McpServerStatus.REGISTERED

    def test_sse_server(self):
        s = McpServer.model_construct(
            name="remote",
            transport_type=TransportType.SSE,
            connection_config={"url": "http://example.com/sse"},
        )
        assert s.transport_type == TransportType.SSE

    def test_http_server(self):
        s = McpServer.model_construct(
            name="api",
            transport_type=TransportType.HTTP,
            connection_config={"url": "http://example.com/api"},
        )
        assert s.transport_type == TransportType.HTTP

    def test_allowed_tools_default_empty(self):
        assert McpServer.model_fields["allowed_tools"].default_factory() == []

    def test_tags_default_empty(self):
        assert McpServer.model_fields["tags"].default_factory() == []

    def test_server_with_tags(self):
        s = McpServer.model_construct(
            name="tagged",
            transport_type=TransportType.STDIO,
            connection_config={"command": "npx"},
            tags=["observability", "ticketing"],
        )
        assert s.tags == ["observability", "ticketing"]


# ── Workflow ─────────────────────────────────────────────────────────────────


class TestWorkflowModel:
    def test_workflow_defaults(self):
        assert Workflow.model_fields["max_turns"].default == 5
        assert Workflow.model_fields["current_turn"].default == 0
        assert Workflow.model_fields["status"].default == WorkflowStatus.ACTIVE
        assert Workflow.model_fields["output_format"].default == OutputFormat.JSON
        assert Workflow.model_fields["infinite_session"].default is True
        assert Workflow.model_fields["caveman"].default is False
        assert Workflow.model_fields["bypass_memory"].default is False
        assert Workflow.model_fields["auto_memory"].default is False
        assert Workflow.model_fields["tsv_tool_results"].default is False

    def test_workflow_status_enum(self):
        assert WorkflowStatus.ACTIVE == "active"
        assert WorkflowStatus.INACTIVE == "inactive"


# ── UsageStats ───────────────────────────────────────────────────────────────


class TestUsageStats:
    def test_defaults(self):
        u = UsageStats()
        assert u.total_premium_requests == 0
        assert u.total_input_tokens == 0
        assert u.total_output_tokens == 0
        assert u.total_cost == 0.0


# ── LogEntry / Message ───────────────────────────────────────────────────────


class TestLogAndMessage:
    def test_log_entry(self):
        le = LogEntry(event="test_event", detail="details here")
        assert le.event == "test_event"
        assert le.tool_input is None
        assert le.tool_output is None

    def test_message(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"
        assert m.tool_calls is None


# ── TaskExecution ────────────────────────────────────────────────────────────


class TestTaskExecutionModel:
    def test_defaults(self):
        assert TaskExecution.model_fields["status"].default == TaskStatus.PENDING
        assert TaskExecution.model_fields["tool_calls"].default == 0

    def test_task_progress(self):
        tp = TaskProgress(
            todos=[
                TodoItem(id=1, title="Step 1", status=TodoItemStatus.COMPLETED),
                TodoItem(id=2, title="Step 2", status=TodoItemStatus.IN_PROGRESS),
            ],
            current_step=2,
            percent_complete=0.5,
        )
        assert len(tp.todos) == 2
        assert tp.percent_complete == 0.5

    def test_todo_item_status_values(self):
        assert TodoItemStatus.NOT_STARTED == "not-started"
        assert TodoItemStatus.IN_PROGRESS == "in-progress"
        assert TodoItemStatus.COMPLETED == "completed"


# ── Token ────────────────────────────────────────────────────────────────────


class TestTokenModel:
    def test_token_creation(self):
        t = Token.model_construct(
            name="github",
            encrypted_value="encrypted123",
            description="GitHub PAT",
            created_by="admin",
        )
        assert t.name == "github"
        assert t.encrypted_value == "encrypted123"
