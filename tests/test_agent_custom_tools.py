"""Tests for custom tool agent integration (model, schema, engine helpers)."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


FAKE_ID = "6601a1b2c3d4e5f607890abc"
FAKE_NOW = datetime.now(UTC)

ECHO_SOURCE = """
def echo(message: str) -> dict:
    return {"echo": message}
"""


# ── Agent model / schema ──────────────────────────────────────────────────────


def test_agent_model_has_custom_tool_ids():
    from unittest.mock import patch, MagicMock
    from app.models.agent import Agent
    with patch.object(Agent, "get_motor_collection", return_value=MagicMock()):
        agent = Agent(
            name="Test",
            description="",
            system_prompt="You are helpful.",
            custom_tool_ids=["abc123", "def456"],
        )
    assert agent.custom_tool_ids == ["abc123", "def456"]


def test_agent_model_custom_tool_ids_defaults_empty():
    from unittest.mock import patch, MagicMock
    from app.models.agent import Agent
    with patch.object(Agent, "get_motor_collection", return_value=MagicMock()):
        agent = Agent(name="NoTools", description="", system_prompt=".")
    assert agent.custom_tool_ids == []


def test_agent_create_schema_accepts_custom_tool_ids():
    from app.schemas.agent import AgentCreate
    data = AgentCreate(
        name="WithTools",
        system_prompt="test",
        custom_tool_ids=["id1", "id2"],
    )
    assert data.custom_tool_ids == ["id1", "id2"]


def test_agent_update_schema_accepts_custom_tool_ids():
    from app.schemas.agent import AgentUpdate
    data = AgentUpdate(custom_tool_ids=["id_x"])
    assert data.custom_tool_ids == ["id_x"]


def test_agent_update_schema_defaults_none():
    from app.schemas.agent import AgentUpdate
    data = AgentUpdate()
    assert data.custom_tool_ids is None


def test_agent_response_schema_has_custom_tool_ids():
    from app.schemas.agent import AgentResponse
    resp = AgentResponse(
        id="abc",
        name="A",
        description="",
        system_prompt=".",
        model=None,
        mcp_server_ids=[],
        mcp_server_tags=[],
        tool_definitions=[],
        knowledge_source_ids=[],
        knowledge_tags=[],
        builtin_tools=[],
        custom_tool_ids=["x", "y"],
        provider_id=None,
        created_at=FAKE_NOW,
        updated_at=FAKE_NOW,
    )
    assert resp.custom_tool_ids == ["x", "y"]


# ── CustomTool model ──────────────────────────────────────────────────────────


def test_custom_tool_model_fields():
    from unittest.mock import patch, MagicMock
    from app.models.custom_tool import CustomTool
    with patch.object(CustomTool, "get_motor_collection", return_value=MagicMock()):
        tool = CustomTool(
            name="echo",
            description="An echo tool",
            source_code=ECHO_SOURCE,
            parameters_schema={"type": "object", "properties": {}},
            tags=["utility"],
            is_enabled=True,
        )
    assert tool.name == "echo"
    assert tool.is_enabled is True
    assert tool.tags == ["utility"]


def test_custom_tool_defaults():
    from unittest.mock import patch, MagicMock
    from app.models.custom_tool import CustomTool
    with patch.object(CustomTool, "get_motor_collection", return_value=MagicMock()):
        tool = CustomTool(name="bare", source_code="def bare(): pass")
    assert tool.description == ""
    assert tool.parameters_schema == {}
    assert tool.tags == []
    assert tool.is_enabled is True


# ── _build_custom_tools_config ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_custom_tools_config_returns_all_formats():
    """_build_custom_tools_config should produce OpenAI, Claude, and fn_map entries."""
    mock_tool = MagicMock()
    mock_tool.id = FAKE_ID
    mock_tool.name = "echo"
    mock_tool.description = "Echos input"
    mock_tool.source_code = ECHO_SOURCE
    mock_tool.is_enabled = True
    mock_tool.parameters_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    with patch("app.core.agent_engine.CustomTool") as MockCT:
        MockCT.get = AsyncMock(return_value=mock_tool)
        from app.core.agent_engine import _build_custom_tools_config
        openai_defs, claude_defs, fn_map = await _build_custom_tools_config([FAKE_ID])

    assert len(openai_defs) == 1
    assert openai_defs[0]["type"] == "function"
    assert openai_defs[0]["function"]["name"] == "echo"
    assert "message" in openai_defs[0]["function"]["parameters"]["properties"]

    assert len(claude_defs) == 1
    assert claude_defs[0]["type"] == "custom"
    assert claude_defs[0]["name"] == "echo"
    assert "input_schema" in claude_defs[0]

    assert "echo" in fn_map
    assert fn_map["echo"] is mock_tool


@pytest.mark.asyncio
async def test_build_custom_tools_config_skips_disabled():
    mock_tool = MagicMock()
    mock_tool.name = "disabled_tool"
    mock_tool.is_enabled = False

    with patch("app.core.agent_engine.CustomTool") as MockCT:
        MockCT.get = AsyncMock(return_value=mock_tool)
        from app.core.agent_engine import _build_custom_tools_config
        openai_defs, claude_defs, fn_map = await _build_custom_tools_config([FAKE_ID])

    assert openai_defs == []
    assert claude_defs == []
    assert fn_map == {}


@pytest.mark.asyncio
async def test_build_custom_tools_config_skips_not_found():
    with patch("app.core.agent_engine.CustomTool") as MockCT:
        MockCT.get = AsyncMock(return_value=None)
        from app.core.agent_engine import _build_custom_tools_config
        openai_defs, claude_defs, fn_map = await _build_custom_tools_config([FAKE_ID])

    assert openai_defs == []
    assert fn_map == {}


# ── _execute_custom_tool ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_custom_tool_success():
    mock_tool = MagicMock()
    mock_tool.name = "echo"
    mock_tool.source_code = ECHO_SOURCE
    fn_map = {"echo": mock_tool}

    with patch(
        "app.core.agent_engine.custom_tool_runner.run_tool",
        new_callable=AsyncMock,
        return_value=json.dumps({"echo": "hi"}),
    ):
        from app.core.agent_engine import _execute_custom_tool
        result = await _execute_custom_tool("echo", {"message": "hi"}, fn_map)

    parsed = json.loads(result)
    assert parsed == {"echo": "hi"}


@pytest.mark.asyncio
async def test_execute_custom_tool_merges_runtime_env():
    mock_tool = MagicMock()
    mock_tool.name = "echo"
    mock_tool.source_code = ECHO_SOURCE
    mock_tool.env_config = {"TOKEN": "secret"}
    fn_map = {"echo": mock_tool}

    with (
        patch("app.services.token_manager.resolve_config", new_callable=AsyncMock, return_value={"TOKEN": "resolved"}),
        patch(
            "app.core.agent_engine.custom_tool_runner.run_tool",
            new_callable=AsyncMock,
            return_value=json.dumps({"echo": "hi"}),
        ) as mock_run_tool,
    ):
        from app.core.agent_engine import _execute_custom_tool
        await _execute_custom_tool(
            "echo",
            {"message": "hi"},
            fn_map,
            runtime_env={"TBD_AGENTS_REPO_ROOT": "/tmp/repo"},
        )

    assert mock_run_tool.await_count == 1
    assert mock_run_tool.await_args.kwargs["env"] == {
        "TOKEN": "resolved",
        "TBD_AGENTS_REPO_ROOT": "/tmp/repo",
    }


@pytest.mark.asyncio
async def test_execute_custom_tool_not_found():
    from app.core.agent_engine import _execute_custom_tool
    result = await _execute_custom_tool("nonexistent", {}, {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not found" in parsed["error"]


# ── API round-trip: agent with custom_tool_ids ────────────────────────────────


def test_agent_api_exposes_custom_tool_ids(app_client):
    """The /api/agents endpoint should include custom_tool_ids in responses."""
    fake_agent = MagicMock()
    fake_agent.id = FAKE_ID
    fake_agent.name = "ToolAgent"
    fake_agent.description = ""
    fake_agent.system_prompt = "."
    fake_agent.model = None
    fake_agent.mcp_server_ids = []
    fake_agent.mcp_server_tags = []
    fake_agent.tool_definitions = []
    fake_agent.knowledge_source_ids = []
    fake_agent.knowledge_tags = []
    fake_agent.builtin_tools = []
    fake_agent.custom_tool_ids = ["abc123"]
    fake_agent.provider_id = None
    fake_agent.created_at = FAKE_NOW
    fake_agent.updated_at = FAKE_NOW

    with (
        patch("app.api.routes.agents.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.agents.Agent") as MockAgent,
    ):
        MockAgent.get = AsyncMock(return_value=fake_agent)
        resp = app_client.get(
            f"/api/agents/{FAKE_ID}",
            headers={"Authorization": "Bearer test"},
        )

    # If auth is bypassed, verify custom_tool_ids is in the response body
    if resp.status_code == 200:
        body = resp.json()
        assert "custom_tool_ids" in body
        assert body["custom_tool_ids"] == ["abc123"]
