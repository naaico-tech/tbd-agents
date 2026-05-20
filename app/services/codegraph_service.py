"""CodeGraph service — delegates repo lifecycle to the codegraph-sidecar container.

All heavy work (git clone, codegraph init/index) runs inside the dedicated
``codegraph-sidecar`` container.  This service owns the tbd-agents database
records (CodeGraphRepo, McpServer) and is the authoritative source of status
within the platform.

Transport:  httpx async HTTP client → codegraph-sidecar REST API
MCP access: agents connect to the sidecar's per-repo SSE endpoint, registered
            automatically as an McpServer record after indexing completes.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.db import parse_doc_id
from app.models.codegraph_repo import CodeGraphRepo, CodeGraphRepoStatus
from app.models.mcp_server import McpServer, TransportType

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MCP_TOOLS = [
    "codegraph_search",
    "codegraph_context",
    "codegraph_callers",
    "codegraph_callees",
    "codegraph_impact",
    "codegraph_node",
    "codegraph_explore",
    "codegraph_files",
    "codegraph_status",
]

# Seconds between polling the sidecar for indexing status updates.
_POLL_INTERVAL = 15

_SIDECAR_STATUS_MAP = {
    "pending": CodeGraphRepoStatus.PENDING,
    "cloning": CodeGraphRepoStatus.CLONING,
    "indexing": CodeGraphRepoStatus.INDEXING,
    "ready": CodeGraphRepoStatus.READY,
    "error": CodeGraphRepoStatus.ERROR,
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _slugify(name: str) -> str:
    """Mirror the sidecar's slugify logic: spaces/slashes → underscores, strip unsafe chars."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "", name.replace(" ", "_").replace("/", "_").replace("\\", "_"))


async def _fail(repo: CodeGraphRepo, message: str) -> None:
    """Transition *repo* to the ERROR state and persist."""
    logger.error("CodeGraph repo '%s' failed: %s", repo.name, message)
    repo.status = CodeGraphRepoStatus.ERROR
    repo.error_message = message
    repo.updated_at = datetime.now(UTC)
    await repo.save()


# ── Service class ─────────────────────────────────────────────────────────────


class CodeGraphService:
    """Manages the lifecycle of code repositories indexed by the codegraph sidecar."""

    def _url(self, path: str) -> str:
        return f"{settings.codegraph_sidecar_url.rstrip('/')}{path}"

    # ── MCP server helpers ────────────────────────────────────────────────────

    async def ensure_mcp_server(self, repo: CodeGraphRepo) -> Any:
        """Find or create the SSE :class:`McpServer` record for *repo*.

        The server points at the sidecar's per-repo SSE endpoint:
            GET {sidecar_url}/repos/{slug}/sse

        tbd-agents' MCP registry spawns an SSE client to this URL each time
        an agent with this MCP server assigned starts a turn.
        """
        server_name = f"code-graph-{repo.name}"
        existing = await McpServer.find_one(McpServer.name == server_name)
        if existing is not None:
            logger.debug("Found existing MCP server record '%s'.", server_name)
            return existing

        slug = _slugify(repo.name)
        sse_url = self._url(f"/repos/{slug}/sse")
        logger.info("Creating MCP server record '%s' → %s", server_name, sse_url)

        mcp_server = McpServer(
            name=server_name,
            transport_type=TransportType.SSE,
            connection_config={"url": sse_url},
            allowed_tools=MCP_TOOLS,
            tags=["code-analysis", "graph"],
        )
        await mcp_server.insert()
        return mcp_server

    # ── Full indexing lifecycle ───────────────────────────────────────────────

    async def index_repository(self, repo_url: str, name: str, repo_id: str) -> None:
        """Delegate cloning and indexing to the sidecar, then register the MCP server.

        Status transitions mirror what the sidecar reports:
        ``PENDING`` → ``CLONING`` → ``INDEXING`` → ``READY`` (or ``ERROR``).
        """
        repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
        if repo is None:
            raise ValueError(f"CodeGraphRepo with id={repo_id!r} not found.")

        slug = _slugify(name)

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=1800.0)) as client:
            # ── POST to sidecar — triggers async clone + index ────────────────
            try:
                resp = await client.post(
                    self._url("/repos"),
                    json={
                        "name": name,
                        "repoUrl": repo_url,
                        "cloneDepth": settings.codegraph_clone_depth,
                    },
                )
                resp.raise_for_status()
                sidecar_data = resp.json()
                slug = sidecar_data.get("slug", slug)
            except httpx.HTTPStatusError as exc:
                await _fail(repo, f"Sidecar rejected repo registration: {exc.response.text}")
                return
            except httpx.HTTPError as exc:
                await _fail(repo, f"Could not reach codegraph sidecar: {exc}")
                return

            repo.local_path = sidecar_data.get("localPath", f"/opt/codegraph_repos/{slug}")
            repo.status = CodeGraphRepoStatus.CLONING
            repo.updated_at = datetime.now(UTC)
            await repo.save()

            # ── Poll sidecar until indexing finishes ──────────────────────────
            while True:
                await asyncio.sleep(_POLL_INTERVAL)

                try:
                    poll = await client.get(self._url(f"/repos/{slug}"))
                    poll.raise_for_status()
                    sidecar_status = poll.json()
                except httpx.HTTPError as exc:
                    logger.warning("Sidecar poll failed (will retry): %s", exc)
                    continue

                sidecar_state = sidecar_status.get("status", "pending")
                new_status = _SIDECAR_STATUS_MAP.get(sidecar_state, CodeGraphRepoStatus.PENDING)

                if repo.status != new_status:
                    repo.status = new_status
                    repo.updated_at = datetime.now(UTC)
                    await repo.save()

                if sidecar_state == "ready":
                    break

                if sidecar_state == "error":
                    error_msg = sidecar_status.get("error", "Sidecar indexing failed")
                    await _fail(repo, error_msg)
                    raise RuntimeError(error_msg)

        # ── Register the MCP server (SSE transport) ───────────────────────────
        try:
            mcp_server = await self.ensure_mcp_server(repo)
            repo.mcp_server_id = str(mcp_server.id)
            repo.status = CodeGraphRepoStatus.READY
            repo.indexed_at = datetime.now(UTC)
            repo.updated_at = datetime.now(UTC)
            await repo.save()
            logger.info(
                "Repository '%s' is READY (mcp_server_id=%s).", name, repo.mcp_server_id
            )
        except Exception as exc:  # noqa: BLE001
            await _fail(repo, str(exc))
            raise

    # ── Re-index ──────────────────────────────────────────────────────────────

    async def reindex_repository(self, repo_id: str) -> None:
        """Trigger a re-index via the sidecar for *repo_id*.

        Delegates to :meth:`index_repository` which calls ``POST /repos`` on the
        sidecar.  The sidecar detects the repo already exists and runs
        ``git pull`` + ``codegraph index`` instead of a fresh clone.
        """
        repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
        if repo is None:
            raise ValueError(f"CodeGraphRepo with id={repo_id!r} not found.")

        repo.status = CodeGraphRepoStatus.PENDING
        repo.updated_at = datetime.now(UTC)
        await repo.save()

        await self.index_repository(
            repo_url=repo.repo_url, name=repo.name, repo_id=repo_id
        )

    # ── Remove ────────────────────────────────────────────────────────────────

    async def remove_repository(self, repo_id: str, delete_local: bool = False) -> None:
        """Remove a repository from the sidecar and from tbd-agents records."""
        repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
        if repo is None:
            raise ValueError(f"CodeGraphRepo with id={repo_id!r} not found.")

        slug = _slugify(repo.name)

        # Ask sidecar to remove (best-effort — don't fail the whole operation)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(
                    self._url(f"/repos/{slug}"),
                    params={"deleteLocal": "true" if delete_local else "false"},
                )
        except httpx.HTTPError as exc:
            logger.warning("Sidecar delete call failed for '%s' (ignored): %s", repo.name, exc)

        # Remove the associated MCP server record.
        if repo.mcp_server_id:
            mcp_server = await McpServer.get(parse_doc_id(repo.mcp_server_id))
            if mcp_server is not None:
                logger.info("Deleting MCP server record '%s'.", mcp_server.name)
                await mcp_server.delete()

        await repo.delete()
        logger.info("Deleted CodeGraphRepo record for '%s'.", repo.name)

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_repositories(self) -> list[CodeGraphRepo]:
        """Return all :class:`CodeGraphRepo` documents."""
        return await CodeGraphRepo.find_all().to_list()

    # ── Ad-hoc query ──────────────────────────────────────────────────────────

    async def query_cli(self, command: str, args: list[str], repo_id: str) -> dict:
        """Proxy a ``codegraph <command> --json`` query to the sidecar.

        Parameters
        ----------
        command:
            The codegraph sub-command (e.g. ``"search"``, ``"callers"``).
        args:
            Additional CLI arguments passed after ``--json``.
        repo_id:
            The tbd-agents document ID of the :class:`CodeGraphRepo`.
        """
        repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
        if repo is None:
            raise ValueError(f"CodeGraphRepo with id={repo_id!r} not found.")

        slug = _slugify(repo.name)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._url(f"/repos/{slug}/query"),
                json={"command": command, "args": args},
            )
            resp.raise_for_status()
            return resp.json()


# ── Module-level singleton ────────────────────────────────────────────────────

codegraph_service = CodeGraphService()
