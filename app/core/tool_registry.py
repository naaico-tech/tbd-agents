"""Build SDK-compatible MCP server and tool configurations from DB models."""

import logging
import os
from typing import Any

from app.models.mcp_server import McpServer, TransportType

logger = logging.getLogger(__name__)


def build_mcp_servers_config(servers: list[McpServer]) -> dict[str, dict[str, Any]]:
    """Convert DB McpServer records into the Copilot SDK mcp_servers format.

    Returns a dict keyed by server name with stdio/sse config dicts.
    """
    config: dict[str, dict[str, Any]] = {}
    for server in servers:
        cc = server.connection_config
        if server.transport_type == TransportType.STDIO:
            # Merge host env with config-supplied env so PATH/NODE_PATH are available
            env = dict(os.environ)
            if cc.get("env"):
                env.update(cc["env"])
            config[server.name] = {
                "type": "stdio",
                "command": cc["command"],
                "args": cc.get("args", []),
                "env": env,
            }
        elif server.transport_type == TransportType.SSE:
            config[server.name] = {
                "type": "sse",
                "url": cc["url"],
                "headers": cc.get("headers", {}),
            }
    return config
