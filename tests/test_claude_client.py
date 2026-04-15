"""Tests for the Claude SDK client builder and agent_engine Claude path."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import _mcp_tool_to_claude
from app.services.claude_client import build_claude_client


# ── Client builder tests ─────────────────────────────────────────────────────


class TestBuildClaudeClient:
    @patch("app.services.claude_client.AsyncAnthropic")
    def test_creates_client_with_api_key(self, MockAsyncAnthropic):
        MockAsyncAnthropic.return_value = MagicMock()
        client = build_claude_client("sk-ant-test-key")
        MockAsyncAnthropic.assert_called_once_with(api_key="sk-ant-test-key")

    @patch("app.services.claude_client.AsyncAnthropic")
    def test_returns_client_instance(self, MockAsyncAnthropic):
        mock_client = MagicMock()
        MockAsyncAnthropic.return_value = mock_client
        result = build_claude_client("sk-ant-test")
        assert result is mock_client


# ── Tool format mapping tests ────────────────────────────────────────────────


class TestMcpToolToClaude:
    def test_basic_tool_conversion(self):
        tool = SimpleNamespace(
            name="read_file",
            description="Read a file from disk",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        )
        result = _mcp_tool_to_claude(tool)
        assert result["name"] == "read_file"
        assert result["description"] == "Read a file from disk"
        assert result["input_schema"]["type"] == "object"
        assert "path" in result["input_schema"]["properties"]
        assert result["input_schema"]["required"] == ["path"]

    def test_empty_schema_gets_defaults(self):
        tool = SimpleNamespace(
            name="no_params",
            description="A tool with no params",
            inputSchema=None,
        )
        result = _mcp_tool_to_claude(tool)
        assert result["name"] == "no_params"
        assert result["input_schema"]["type"] == "object"
        assert result["input_schema"]["properties"] == {}

    def test_missing_description_defaults_empty(self):
        tool = SimpleNamespace(
            name="tool_x",
            description=None,
            inputSchema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        result = _mcp_tool_to_claude(tool)
        assert result["description"] == ""

    def test_schema_without_type_gets_default(self):
        tool = SimpleNamespace(
            name="partial",
            description="Partial schema",
            inputSchema={"properties": {"a": {"type": "string"}}},
        )
        result = _mcp_tool_to_claude(tool)
        assert result["input_schema"]["type"] == "object"

    def test_does_not_use_openai_function_wrapper(self):
        """Claude tools should NOT be wrapped in {type: function, function: {...}}."""
        tool = SimpleNamespace(
            name="my_tool",
            description="desc",
            inputSchema={"type": "object", "properties": {}},
        )
        result = _mcp_tool_to_claude(tool)
        assert "type" not in result or result.get("type") != "function"
        assert "function" not in result
        assert "input_schema" in result


# ── Execution path branching test ────────────────────────────────────────────


class TestClaudeExecutionRouting:
    """Test that ANTHROPIC provider type routes to _run_with_claude_sdk."""

    @pytest.mark.asyncio
    async def test_anthropic_routes_to_claude_sdk(self):
        """Verify that run_agent calls _run_with_claude_sdk for ANTHROPIC providers."""
        from app.models.provider import ProviderType

        with (
            patch("app.core.agent_engine.Agent") as MockAgent,
            patch("app.core.agent_engine.Provider") as MockProvider,
            patch("app.core.agent_engine.TaskExecution"),
            patch("app.core.agent_engine.Workflow"),
            patch("app.core.agent_engine.token_manager") as mock_tm,
            patch("app.core.agent_engine._run_with_claude_sdk", new_callable=AsyncMock) as mock_claude,
            patch("app.core.agent_engine._run_with_custom_provider", new_callable=AsyncMock) as mock_custom,
            patch("app.core.agent_engine._build_system_prompt", new_callable=AsyncMock) as mock_sp,
            patch("app.core.agent_engine._log", new_callable=AsyncMock),
            patch("app.core.agent_engine._publish_status", new_callable=AsyncMock),
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock) as mock_repo,
            patch("app.core.agent_engine.build_mcp_servers_config", new_callable=AsyncMock) as mock_mcp,
            patch("app.core.agent_engine.knowledge_manager") as mock_km,
            patch("app.core.agent_engine.McpServer"),
            patch("app.core.agent_engine.KnowledgeSource"),
        ):
            # Setup mocks
            mock_agent = AsyncMock()
            mock_agent.provider_id = "6612f1a2b3c4d5e6f7890123"
            mock_agent.mcp_server_ids = []
            mock_agent.mcp_server_tags = []
            mock_agent.knowledge_source_ids = []
            mock_agent.knowledge_tags = []
            mock_agent.system_prompt = "test"
            MockAgent.get = AsyncMock(return_value=mock_agent)

            mock_provider = MagicMock()
            mock_provider.name = "my-claude"
            mock_provider.provider_type = ProviderType.ANTHROPIC
            mock_provider.api_key_token_name = "claude-key"
            MockProvider.get = AsyncMock(return_value=mock_provider)

            mock_tm.get_token_value = AsyncMock(return_value="sk-ant-test-key")
            mock_sp.return_value = "system prompt"
            mock_repo.return_value = None
            mock_mcp.return_value = {}
            mock_km.build_knowledge_context = AsyncMock(return_value="")
            mock_claude.return_value = "Claude response"

            # Create workflow mock
            workflow = MagicMock()
            workflow.id = "wf-123"
            workflow.status = "active"
            workflow.agent_id = "agent-123"
            workflow.model = "claude-sonnet-4-20250514"
            workflow.max_turns = 10
            workflow.skill_ids = []
            workflow.messages = []
            workflow.repo_url = None
            workflow.infinite_session = False
            workflow.save = AsyncMock()

            from app.core.agent_engine import run_agent

            result = await run_agent(workflow, "Hello Claude", "ghp_token")

            # Verify _run_with_claude_sdk was called, NOT _run_with_custom_provider
            mock_claude.assert_called_once()
            mock_custom.assert_not_called()
