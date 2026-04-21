"""Tests for Pydantic schemas (request/response validation)."""

import pytest
from pydantic import ValidationError

from app.models.guardrail import GuardrailType
from app.schemas.agent import AgentCreate, AgentUpdate
from app.schemas.guardrail import GuardrailCreate, GuardrailUpdate
from app.schemas.mcp import McpServerCreate, McpServerUpdate, McpTestResponse
from app.schemas.skill import SkillCreate, SkillUpdate
from app.schemas.token import TokenCreate, TokenUpdate
from app.schemas.workflow import (
    PromptRequest,
    WorkflowCreate,
    WorkflowUpdate,
)

# ── Agent schemas ────────────────────────────────────────────────────────────


class TestAgentSchemas:
    def test_create_minimal(self):
        c = AgentCreate(name="agent1")
        assert c.name == "agent1"
        assert c.system_prompt == "You are a helpful assistant."
        assert c.mcp_server_ids == []

    def test_create_full(self):
        c = AgentCreate(
            name="agent2",
            description="Full agent",
            system_prompt="Be concise.",
            model="gpt-4.1",
            mcp_server_ids=["s1"],
            mcp_server_tags=["data", "messaging"],
            tool_definitions=[{"type": "function", "name": "search"}],
        )
        assert c.model == "gpt-4.1"
        assert len(c.tool_definitions) == 1
        assert c.mcp_server_tags == ["data", "messaging"]

    def test_update_partial(self):
        u = AgentUpdate(name="new-name")
        assert u.name == "new-name"
        assert u.description is None

    def test_create_missing_name(self):
        with pytest.raises(ValidationError):
            AgentCreate()


# ── Skill schemas ────────────────────────────────────────────────────────────


class TestSkillSchemas:
    def test_create(self):
        s = SkillCreate(name="coder", instructions="Write code.")
        assert s.name == "coder"
        assert s.tags == []

    def test_update(self):
        u = SkillUpdate(tags=["python", "rust"])
        assert u.tags == ["python", "rust"]
        assert u.name is None

    def test_create_missing_instructions(self):
        with pytest.raises(ValidationError):
            SkillCreate(name="incomplete")


# ── Guardrail schemas ───────────────────────────────────────────────────────


class TestGuardrailSchemas:
    def test_prompt_guardrail_create(self):
        g = GuardrailCreate(
            name="no-secrets",
            guardrail_type=GuardrailType.PROMPT,
            prompt_config={"forbidden_patterns": ["password|secret"]},
        )
        assert g.prompt_config.forbidden_patterns == ["password|secret"]

    def test_prompt_guardrail_missing_config(self):
        with pytest.raises(ValidationError, match="prompt_config is required"):
            GuardrailCreate(
                name="bad",
                guardrail_type=GuardrailType.PROMPT,
            )

    def test_request_guardrail_create(self):
        g = GuardrailCreate(
            name="schema-v1",
            guardrail_type=GuardrailType.REQUEST,
            request_config={"json_schema": {"type": "object"}},
        )
        assert g.request_config.json_schema == {"type": "object"}

    def test_guardrail_update(self):
        u = GuardrailUpdate(enabled=False)
        assert u.enabled is False
        assert u.name is None


# ── MCP schemas ──────────────────────────────────────────────────────────────


class TestMcpSchemas:
    def test_create_stdio(self):
        m = McpServerCreate(
            name="notion",
            transport_type="stdio",
            connection_config={"command": "npx", "args": []},
        )
        assert m.transport_type == "stdio"
        assert m.tags == []

    def test_create_with_tags(self):
        m = McpServerCreate(
            name="notion",
            transport_type="stdio",
            connection_config={"command": "npx", "args": []},
            tags=["documentation", "productivity"],
        )
        assert m.tags == ["documentation", "productivity"]

    def test_create_sse(self):
        m = McpServerCreate(
            name="remote",
            transport_type="sse",
            connection_config={"url": "http://example.com"},
        )
        assert m.connection_config["url"] == "http://example.com"

    def test_update(self):
        u = McpServerUpdate(allowed_tools=["tool1", "tool2"])
        assert len(u.allowed_tools) == 2

    def test_test_response(self):
        r = McpTestResponse(success=True, tools=[{"name": "tool1"}])
        assert r.success is True

    def test_test_response_failure(self):
        r = McpTestResponse(success=False, error="Connection refused")
        assert r.error == "Connection refused"


# ── Token schemas ────────────────────────────────────────────────────────────


class TestTokenSchemas:
    def test_create(self):
        t = TokenCreate(name="gh", value="ghp_1234")
        assert t.name == "gh"
        assert t.description == ""

    def test_update(self):
        u = TokenUpdate(description="Updated desc")
        assert u.value is None

    def test_create_missing_value(self):
        with pytest.raises(ValidationError):
            TokenCreate(name="bad")


# ── Workflow schemas ─────────────────────────────────────────────────────────


class TestWorkflowSchemas:
    def test_create_minimal(self):
        w = WorkflowCreate(agent_id="abc123")
        assert w.agent_id == "abc123"
        assert w.output_format == "json"
        assert w.infinite_session is True
        assert w.caveman is False
        assert w.bypass_memory is False
        assert w.auto_memory is False

    def test_create_full(self):
        w = WorkflowCreate(
            title="My Workflow",
            agent_id="abc",
            max_turns=10,
            output_format="markdown",
            model="gpt-4.1",
            skill_ids=["s1"],
            reasoning_effort="high",
            guardrail_ids=["g1"],
            guardrail_tags=["safety"],
            repo_url="https://github.com/test/repo",
            repo_branch="develop",
            caveman=True,
            bypass_memory=True,
            auto_memory=True,
        )
        assert w.model == "gpt-4.1"
        assert w.caveman is True
        assert w.bypass_memory is True
        assert w.auto_memory is True

    def test_update(self):
        u = WorkflowUpdate(
            max_turns=20,
            reasoning_effort="low",
            caveman=True,
            bypass_memory=True,
            auto_memory=True,
        )
        assert u.max_turns == 20
        assert u.model is None
        assert u.caveman is True
        assert u.bypass_memory is True
        assert u.auto_memory is True

    def test_prompt_request_prompt_only(self):
        p = PromptRequest(prompt="Hello")
        assert p.prompt == "Hello"
        assert p.request is None

    def test_prompt_request_request_only(self):
        p = PromptRequest(request={"query": "search term"})
        assert p.request["query"] == "search term"
        assert p.prompt is None
