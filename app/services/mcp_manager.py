import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.models.mcp_server import McpServer, McpServerStatus, TransportType
from app.services import token_manager

logger = logging.getLogger(__name__)


class McpManager:
    """Manages connections to external MCP servers."""

    def __init__(self) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._cleanup_fns: dict[str, Any] = {}

    @staticmethod
    async def _build_env(config_env: dict | None) -> dict[str, str]:
        """Merge config-supplied env vars with the host process env.

        StdioServerParameters.env replaces the entire environment, so we
        must carry over PATH, HOME, NODE_PATH etc. for npx to work, then
        overlay any credentials the user supplied.

        Any ``{{token:NAME}}`` references in values are resolved from the
        encrypted token store.
        """
        env = dict(os.environ)
        if config_env:
            resolved = await token_manager.resolve_config(config_env)
            env.update(resolved)
        return env

    @asynccontextmanager
    async def _connect_stdio(self, config: dict):
        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env=await self._build_env(config.get("env")),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @asynccontextmanager
    async def _connect_sse(self, config: dict):
        url = config["url"]
        headers = config.get("headers", {})
        if headers:
            headers = await token_manager.resolve_config(headers)
        async with sse_client(url=url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def test_connection(self, server: McpServer) -> dict[str, Any]:
        """Test MCP server connectivity. Returns {success, tools[], error?}."""
        try:
            ctx = (
                self._connect_stdio(server.connection_config)
                if server.transport_type == TransportType.STDIO
                else self._connect_sse(server.connection_config)
            )
            async with ctx as session:
                result = await session.list_tools()
                tools = [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                    }
                    for t in result.tools
                ]
                server.status = McpServerStatus.CONNECTED
                server.last_error = None
                await server.save()
                return {"success": True, "tools": tools}
        except Exception as e:
            server.status = McpServerStatus.ERROR
            server.last_error = str(e)
            await server.save()
            return {"success": False, "tools": [], "error": str(e)}

    async def list_tools(self, server: McpServer) -> list[dict[str, Any]]:
        """List tools from an MCP server (ephemeral connection)."""
        ctx = (
            self._connect_stdio(server.connection_config)
            if server.transport_type == TransportType.STDIO
            else self._connect_sse(server.connection_config)
        )
        async with ctx as session:
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                }
                for t in result.tools
            ]

    async def call_tool(
        self, server: McpServer, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call a tool on the MCP server and return the result."""
        ctx = (
            self._connect_stdio(server.connection_config)
            if server.transport_type == TransportType.STDIO
            else self._connect_sse(server.connection_config)
        )
        async with ctx as session:
            result = await session.call_tool(tool_name, arguments)
            # Extract text content from the result
            contents = []
            for item in result.content:
                if hasattr(item, "text"):
                    contents.append(item.text)
                else:
                    contents.append(str(item))
            return "\n".join(contents) if contents else ""


# Singleton instance
mcp_manager = McpManager()
