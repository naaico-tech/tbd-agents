"""Tests for the tool_registry module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.tool_registry import build_mcp_servers_config
from app.models.mcp_server import TransportType


def _make_server(name, transport_type, connection_config, allowed_tools=None):
    """Build a mock McpServer to avoid Beanie init."""
    s = MagicMock()
    s.name = name
    s.transport_type = transport_type
    s.connection_config = connection_config
    s.allowed_tools = allowed_tools or []
    return s


class TestBuildMcpServersConfig:
    @pytest.mark.asyncio
    async def test_stdio_server(self):
        server = _make_server(
            "notion",
            TransportType.STDIO,
            {"command": "npx", "args": ["-y", "notion-mcp"]},
        )
        with patch("app.core.tool_registry.token_manager") as mock_tm:
            mock_tm.resolve_config = AsyncMock(return_value={})
            config = await build_mcp_servers_config([server])

        assert "notion" in config
        assert config["notion"]["type"] == "stdio"
        assert config["notion"]["command"] == "npx"
        assert config["notion"]["tools"] == ["*"]

    @pytest.mark.asyncio
    async def test_sse_server(self):
        server = _make_server(
            "remote",
            TransportType.SSE,
            {"url": "http://example.com/sse", "headers": {}},
        )
        with patch("app.core.tool_registry.token_manager") as mock_tm:
            mock_tm.resolve_config = AsyncMock(return_value={})
            config = await build_mcp_servers_config([server])

        assert "remote" in config
        assert config["remote"]["type"] == "sse"
        assert config["remote"]["url"] == "http://example.com/sse"

    @pytest.mark.asyncio
    async def test_http_server(self):
        server = _make_server(
            "api",
            TransportType.HTTP,
            {"url": "http://example.com/api", "headers": {"X-Key": "val"}},
        )
        with patch("app.core.tool_registry.token_manager") as mock_tm:
            mock_tm.resolve_config = AsyncMock(return_value={"X-Key": "val"})
            config = await build_mcp_servers_config([server])

        assert config["api"]["type"] == "http"
        assert config["api"]["headers"] == {"X-Key": "val"}

    @pytest.mark.asyncio
    async def test_allowed_tools_filter(self):
        server = _make_server(
            "restricted",
            TransportType.SSE,
            {"url": "http://x"},
            allowed_tools=["search", "read"],
        )
        with patch("app.core.tool_registry.token_manager") as mock_tm:
            mock_tm.resolve_config = AsyncMock(return_value={})
            config = await build_mcp_servers_config([server])

        assert config["restricted"]["tools"] == ["search", "read"]

    @pytest.mark.asyncio
    async def test_empty_server_list(self):
        with patch("app.core.tool_registry.token_manager"):
            config = await build_mcp_servers_config([])
        assert config == {}

    @pytest.mark.asyncio
    async def test_multiple_servers(self):
        servers = [
            _make_server("s1", TransportType.STDIO, {"command": "cmd1"}),
            _make_server("s2", TransportType.SSE, {"url": "http://s2"}),
        ]
        with patch("app.core.tool_registry.token_manager") as mock_tm:
            mock_tm.resolve_config = AsyncMock(return_value={})
            config = await build_mcp_servers_config(servers)

        assert "s1" in config
        assert "s2" in config

    @pytest.mark.asyncio
    async def test_stdio_env_merges_with_os_env(self):
        server = _make_server(
            "env-test",
            TransportType.STDIO,
            {"command": "node", "env": {"CUSTOM_VAR": "value"}},
        )
        with patch("app.core.tool_registry.token_manager") as mock_tm:
            mock_tm.resolve_config = AsyncMock(return_value={"CUSTOM_VAR": "value"})
            config = await build_mcp_servers_config([server])

        # Should have PATH from os.environ plus the custom var
        assert "PATH" in config["env-test"]["env"]
        assert config["env-test"]["env"]["CUSTOM_VAR"] == "value"
