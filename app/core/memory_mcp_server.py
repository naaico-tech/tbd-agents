"""Lightweight stdio MCP server that exposes the ``store_memory`` tool.

This server is spawned as a subprocess by the Copilot SDK execution path
so that ``store_memory`` appears as a regular MCP tool the model can call.
It proxies memory operations back to the TBD Agents API via HTTP.

Usage (automatic — injected by ``agent_engine.run_agent``):

    python -m app.core.memory_mcp_server

Environment variables (set by the parent process):
    AGENT_ID       – The agent ID for scoping memories.
    API_BASE_URL   – Base URL of the TBD Agents API (default: http://localhost:8000).
    API_TOKEN      – Bearer token for API authentication.
"""

import asyncio
import json
import os
import sys

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

AGENT_ID = os.environ.get("AGENT_ID", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
API_TOKEN = os.environ.get("API_TOKEN", "")

server = Server("memory")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="store_memory",
            description=(
                "Save a key-value memory for future reference across conversations. "
                "Use this to remember important facts, decisions, user preferences, "
                "or context that should persist."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "A short descriptive key for the memory",
                    },
                    "value": {
                        "type": "string",
                        "description": "The content to remember",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["session", "agent", "global"],
                        "description": (
                            "Memory scope: session (this workflow), "
                            "agent (this agent), global (all agents)"
                        ),
                        "default": "agent",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata tags",
                    },
                },
                "required": ["key", "value"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "store_memory":
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    key = arguments.get("key", "")
    value = arguments.get("value", "")
    scope = arguments.get("scope", "agent")
    metadata = arguments.get("metadata", {})

    if not key or not value:
        return [TextContent(type="text", text=json.dumps({"error": "Both 'key' and 'value' are required"}))]

    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    payload = {
        "agent_id": AGENT_ID,
        "scope": scope,
        "key": key,
        "value": value,
        "metadata": metadata,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{API_BASE_URL}/api/memories",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 201:
                data = resp.json()
                result = {"status": "stored", "key": data.get("key", key), "scope": data.get("scope", scope)}
            else:
                result = {"error": f"API returned {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        result = {"error": f"Failed to store memory: {exc}"}

    return [TextContent(type="text", text=json.dumps(result))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
