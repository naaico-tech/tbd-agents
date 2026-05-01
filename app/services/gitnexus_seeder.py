"""Startup seeder: auto-register GitNexus MCP server if GITNEXUS_URL is configured."""

import logging
from datetime import UTC, datetime

from app.config import settings
from app.models.mcp_server import McpServer, McpServerStatus, TransportType

logger = logging.getLogger(__name__)

GITNEXUS_MCP_NAME = "gitnexus"
GITNEXUS_MCP_TAGS = ["code", "git", "repository"]


async def seed_gitnexus_mcp() -> None:
    """Upsert the GitNexus MCP server record based on GITNEXUS_URL env setting.

    - If GITNEXUS_URL is unset, this is a no-op (skipped silently).
    - If the record already exists and the URL matches, it is left unchanged.
    - If the record exists with a different URL, the connection_config is updated.
    - If the record does not exist, it is created.
    """
    if not settings.gitnexus_url:
        logger.debug("GITNEXUS_URL not set — skipping GitNexus MCP registration.")
        return

    mcp_url = f"{settings.gitnexus_url.rstrip('/')}/api/mcp"
    existing = await McpServer.find_one(McpServer.name == GITNEXUS_MCP_NAME)

    if existing is None:
        server = McpServer(
            name=GITNEXUS_MCP_NAME,
            transport_type=TransportType.HTTP,
            connection_config={"url": mcp_url},
            tags=GITNEXUS_MCP_TAGS,
            status=McpServerStatus.REGISTERED,
        )
        await server.insert()
        logger.info("GitNexus MCP server registered at %s", mcp_url)
    elif existing.connection_config.get("url") != mcp_url:
        existing.connection_config = {"url": mcp_url}
        existing.tags = list(set(existing.tags) | set(GITNEXUS_MCP_TAGS))
        existing.updated_at = datetime.now(UTC)
        await existing.save()
        logger.info("GitNexus MCP server URL updated to %s", mcp_url)
    else:
        logger.debug("GitNexus MCP server already registered at %s — no change.", mcp_url)
