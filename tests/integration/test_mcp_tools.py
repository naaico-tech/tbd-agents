"""Integration tests: MCP tool invocation through the agent engine.

Verifies MCP server connection, tool discovery, tool execution,
and allowed-tools filtering.

Closes #38
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import run_agent
from app.models.mcp_server import TransportType
from app.models.task_execution import TaskExecution, TaskStatus

from .conftest import (
    create_agent,
    create_mcp_server,
    create_provider,
    create_token,
    create_workflow,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_schema(name: str, description: str = "A test tool"):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        },
    }


def _make_fake_session(captured_mcp_servers: dict):
    """Build mock SDK client + session that captures mcp_servers config and fires events."""
    _on_callback = None

    class _FakeSession:
        session_id = "test-session-mcp"

        class _client:
            @staticmethod
            async def request(*args, **kwargs):
                if _on_callback is None:
                    return
                _on_callback(SimpleNamespace(
                    type=SimpleNamespace(value="assistant.message"),
                    data=SimpleNamespace(content="OK"),
                ))
                _on_callback(SimpleNamespace(
                    type=SimpleNamespace(value="session.idle"),
                    data=None,
                ))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def on(self, callback):
            nonlocal _on_callback
            _on_callback = callback

    def capture_create_session(**kwargs):
        captured_mcp_servers.update(kwargs.get("mcp_servers", {}))
        return _FakeSession()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.create_session = AsyncMock(side_effect=capture_create_session)
    return mock_client


def _sse_text_response(text: str = "Tool result used"):
    """SSE lines for simple text response (no tool calls)."""
    return [
        f'data: {{"choices":[{{"delta":{{"role":"assistant","content":"{text}"}},"finish_reason":null}}]}}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":30,"completion_tokens":10}}',
        "data: [DONE]",
    ]


def _sse_tool_then_text(tool_name, args_json, result_text="Done"):
    """SSE: one tool call → then a text response (simulated two-round)."""
    return [
        # Round 1: tool call
        "data: " + json.dumps({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0, "id": "call_1", "type": "function",
                        "function": {"name": tool_name, "arguments": ""},
                    }]
                },
                "finish_reason": None,
            }]
        }),
        "data: " + json.dumps({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": args_json},
                    }]
                },
                "finish_reason": None,
            }]
        }),
        "data: " + json.dumps({
            "choices": [{
                "delta": {},
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }),
        "data: [DONE]",
    ]


def _make_async_stream(lines, status=200):
    resp = AsyncMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.aclose = AsyncMock()

    async def aiter_lines():
        for line in lines:
            yield line

    resp.aiter_lines = aiter_lines
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMCPToolInvocation:
    @pytest.mark.asyncio
    async def test_tool_discovered_and_injected(self, mock_event_bus):
        """MCP server config is built and passed to the Copilot SDK session."""
        server = await create_mcp_server(
            name="test-stdio-server",
            transport_type=TransportType.STDIO,
            connection_config={"command": "echo", "args": ["hello"]},
        )
        agent = await create_agent(mcp_server_ids=[str(server.id)])
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Use tools", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_mcp: dict = {}

        # The config that build_mcp_servers_config would produce
        fake_mcp_config = {
            "test-stdio-server": {
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "env": {},
                "tools": ["*"],
            }
        }

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.build_mcp_servers_config", new_callable=AsyncMock, return_value=fake_mcp_config),
            patch("app.core.agent_engine.build_client") as mock_build,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_build.return_value = _make_fake_session(captured_mcp)

            await run_agent(wf, "Use tools", "ghp_token", task_execution_id=str(task.id))

        # SDK path passes mcp_servers config to create_session
        assert "test-stdio-server" in captured_mcp
        assert captured_mcp["test-stdio-server"]["type"] == "stdio"

    @pytest.mark.asyncio
    async def test_allowed_tools_filters_tools(self, mock_event_bus):
        """Only allowed tools appear in the MCP config passed to the SDK."""
        server = await create_mcp_server(
            name="filtered-server",
            transport_type=TransportType.STDIO,
            connection_config={"command": "echo", "args": []},
            allowed_tools=["approved_tool"],
        )
        agent = await create_agent(mcp_server_ids=[str(server.id)])
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Filter test", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_mcp: dict = {}

        # build_mcp_servers_config uses allowed_tools directly in config
        fake_mcp_config = {
            "filtered-server": {
                "type": "stdio",
                "command": "echo",
                "args": [],
                "env": {},
                "tools": ["approved_tool"],
            }
        }

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.build_mcp_servers_config", new_callable=AsyncMock, return_value=fake_mcp_config),
            patch("app.core.agent_engine.build_client") as mock_build,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_build.return_value = _make_fake_session(captured_mcp)

            await run_agent(wf, "Filter test", "ghp_token", task_execution_id=str(task.id))

        # SDK config carries the allowed-tools restriction
        assert "filtered-server" in captured_mcp
        assert captured_mcp["filtered-server"]["tools"] == ["approved_tool"]

    @pytest.mark.asyncio
    async def test_copilot_pre_tool_hook_does_not_reapply_global_allowlist(self, mock_event_bus):
        """Copilot SDK should rely on session MCP config instead of a second allowlist gate."""
        server = await create_mcp_server(
            name="filtered-server",
            transport_type=TransportType.STDIO,
            connection_config={"command": "echo", "args": []},
            allowed_tools=["approved_tool"],
        )
        agent = await create_agent(mcp_server_ids=[str(server.id)])
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Filter test", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_hooks: dict = {}

        class _FakeSession:
            session_id = "test-session-mcp-hooks"

            class _client:
                @staticmethod
                async def request(*args, **kwargs):
                    pre_tool = captured_hooks["hooks"]["on_pre_tool_use"]
                    decision = pre_tool({"toolName": "unlisted_runtime_tool"}, None)
                    assert decision["permissionDecision"] == "allow"
                    on_event = captured_hooks["on_event"]
                    on_event(SimpleNamespace(
                        type=SimpleNamespace(value="assistant.message"),
                        data=SimpleNamespace(content="OK"),
                    ))
                    on_event(SimpleNamespace(
                        type=SimpleNamespace(value="session.idle"),
                        data=None,
                    ))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def on(self, callback):
                captured_hooks["on_event"] = callback

        def capture_create_session(**kwargs):
            captured_hooks["hooks"] = kwargs.get("hooks", {})
            return _FakeSession()

        fake_mcp_config = {
            "filtered-server": {
                "type": "stdio",
                "command": "echo",
                "args": [],
                "env": {},
                "tools": ["approved_tool"],
            }
        }

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.build_mcp_servers_config", new_callable=AsyncMock, return_value=fake_mcp_config),
            patch("app.core.agent_engine.build_client") as mock_build,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")

            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.create_session = AsyncMock(side_effect=capture_create_session)
            mock_build.return_value = mock_client

            result = await run_agent(wf, "Filter test", "ghp_token", task_execution_id=str(task.id))

        assert result is not None

    @pytest.mark.asyncio
    async def test_mcp_tool_execution_via_byok(self, mock_event_bus):
        """BYOK path: model requests a tool call → tool executed → result returned."""
        server = await create_mcp_server(
            name="exec-server",
            transport_type=TransportType.STDIO,
            connection_config={"command": "echo", "args": []},
        )
        await create_token("exec-key", "sk-exec")
        from app.models.provider import ProviderType

        provider = await create_provider(
            name="exec-provider",
            provider_type=ProviderType.OPENAI,
            api_key_token_name="exec-key",
        )
        agent = await create_agent(
            provider_id=str(provider.id), mcp_server_ids=[str(server.id)],
        )
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Execute tool", status=TaskStatus.PENDING,
        )
        await task.insert()

        call_count = {"n": 0}

        # First call: tool call, second call: text response
        def make_response():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _make_async_stream(_sse_tool_then_text("search_docs", '{"q":"test"}'))
            return _make_async_stream(_sse_text_response("Tool result used"))

        tool_calls_executed = []

        async def fake_execute_tool(tool_name, arguments, tool_server_map):
            tool_calls_executed.append(tool_name)
            return "Search result: found 3 docs"

        fake_tools = [_make_tool_schema("search_docs")]

        async def fake_connect(mcp_config, allowed, exit_stack):
            return fake_tools, {"search_docs": "exec-server"}

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine._connect_mcp_and_list_tools", side_effect=fake_connect),
            patch("app.core.agent_engine._execute_mcp_tool", side_effect=fake_execute_tool),
            patch("app.core.agent_engine.httpx.AsyncClient") as mock_http_cls,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_http = MagicMock()
            mock_http.send = AsyncMock(side_effect=lambda *a, **kw: make_response())
            mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await run_agent(
                wf, "Execute tool", "ghp_token", task_execution_id=str(task.id),
            )

        assert "search_docs" in tool_calls_executed
        assert result is not None
