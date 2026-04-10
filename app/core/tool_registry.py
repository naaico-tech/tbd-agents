"""Build SDK-compatible MCP server and tool configurations from DB models."""

import logging
import os
from typing import Any

from app.models.mcp_server import McpServer, TransportType
from app.services import token_manager

logger = logging.getLogger(__name__)


async def build_mcp_servers_config(servers: list[McpServer]) -> dict[str, dict[str, Any]]:
    """Convert DB McpServer records into the Copilot SDK mcp_servers format.

    Returns a dict keyed by server name with stdio/sse config dicts.
    Any ``{{token:NAME}}`` references in env values or headers are resolved
    from the encrypted token store.
    """
    config: dict[str, dict[str, Any]] = {}
    for server in servers:
        cc = server.connection_config
        if server.transport_type == TransportType.STDIO:
            # Merge host env with config-supplied env so PATH/NODE_PATH are available
            env = dict(os.environ)
            if cc.get("env"):
                resolved_env = await token_manager.resolve_config(cc["env"])
                env.update(resolved_env)
            config[server.name] = {
                "type": "stdio",
                "command": cc["command"],
                "args": cc.get("args", []),
                "env": env,
            }
        elif server.transport_type == TransportType.SSE:
            headers = cc.get("headers", {})
            if headers:
                headers = await token_manager.resolve_config(headers)
            config[server.name] = {
                "type": "sse",
                "url": cc["url"],
                "headers": headers,
            }
    return config
