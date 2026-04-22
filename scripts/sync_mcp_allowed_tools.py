#!/usr/bin/env python3
"""Sync recommended MCP allowlists into existing MongoDB records.

By default this only tightens servers that are currently unrestricted
(`allowed_tools == []`). Use --force to overwrite an existing explicit list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from app.core.mcp_allowlists import (
    RECOMMENDED_ALLOWED_TOOL_NAMES,
    RECOMMENDED_ALLOWED_TOOL_PREFIXES,
    get_recommended_allowed_tools,
)
from app.db import init_db
from app.models.mcp_server import McpServer
from app.services.mcp_manager import mcp_manager


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing explicit allowlists instead of only filling unrestricted records",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned changes without saving them",
    )
    return parser.parse_args()


async def _sync_server(name: str, force: bool, dry_run: bool) -> list[dict[str, object]]:
    servers = await McpServer.find(McpServer.name == name).to_list()
    results: list[dict[str, object]] = []

    for server in servers:
        available_tool_names: list[str] = []
        list_tools_error: str | None = None
        try:
            available_tools = await mcp_manager.list_tools(server)
            available_tool_names = [str(tool.get("name")) for tool in available_tools]
        except Exception as exc:
            list_tools_error = str(exc)

        desired = get_recommended_allowed_tools(name, available_tool_names=available_tool_names)
        current = list(server.allowed_tools)
        has_rules = bool(
            RECOMMENDED_ALLOWED_TOOL_NAMES.get(name) or RECOMMENDED_ALLOWED_TOOL_PREFIXES.get(name)
        )
        can_update = bool(desired) or not has_rules
        should_update = can_update and current != desired and (force or not current)
        result = {
            "id": str(server.id),
            "name": server.name,
            "tags": list(server.tags),
            "current_allowed_tools": current,
            "recommended_allowed_tools": desired,
            "available_tool_names": available_tool_names,
            "action": "update" if should_update else "skip",
        }
        if list_tools_error is not None:
            result["list_tools_error"] = list_tools_error
        if has_rules and not desired:
            result["action"] = "skip_no_match"
        if should_update and not dry_run:
            server.allowed_tools = desired
            server.updated_at = datetime.now(UTC)
            await server.save()
        results.append(result)

    if not servers:
        results.append({
            "id": None,
            "name": name,
            "tags": [],
            "current_allowed_tools": None,
            "recommended_allowed_tools": desired,
            "action": "missing",
        })
    return results


async def _main(force: bool, dry_run: bool) -> None:
    await init_db()
    results: list[dict[str, object]] = []
    names = set(RECOMMENDED_ALLOWED_TOOL_NAMES) | set(RECOMMENDED_ALLOWED_TOOL_PREFIXES)
    for name in sorted(names):
        results.extend(await _sync_server(name, force=force, dry_run=dry_run))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_main(force=args.force, dry_run=args.dry_run))