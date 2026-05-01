"""CodeRepositoryManager: clone/sync, index, and search for git repos.

Mirrors the responsibilities of ``KnowledgeManager`` for knowledge sources but
applied to git checkouts.  Repos are cached on disk by a deterministic hash of
``url+branch`` so multiple workflows can share a single checkout.  Indexing is
delegated to the GitNexus code-intelligence service.
"""

from __future__ import annotations

import asyncio
import hashlib
import httpx
import logging
import os
import shlex
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.config import settings
from app.models.code_repository import CodeRepository, CodeRepositoryStatus
from app.services import token_manager

if TYPE_CHECKING:
    from app.models.workflow import Workflow

logger = logging.getLogger(__name__)


# ── Manager ──────────────────────────────────────────────────────────────────


class CodeRepositoryManager:
    """Sync, index, and search code repositories."""

    # ── Path helpers ──────────────────────────────────────────────────────

    def _repo_dir(self, repo: CodeRepository) -> str:
        branch = repo.default_branch or "main"
        digest = hashlib.sha256(f"{repo.repo_url}:{branch}".encode()).hexdigest()[:16]
        return os.path.join(settings.repos_base, digest)

    # ── Sync ──────────────────────────────────────────────────────────────

    async def sync(self, repo: CodeRepository, force: bool = False) -> str | None:
        """Clone or fetch+checkout the repo.

        Returns local path on success, ``None`` on failure.  Skips when last
        sync is within ``settings.repo_sync_ttl_seconds`` unless ``force``.
        """
        if not repo.repo_url:
            return None

        # TTL cache — short-circuit if recent and we have a local path
        if not force and repo.last_synced_at and repo.local_path:
            age = (datetime.now(UTC) - repo.last_synced_at).total_seconds()
            if age < settings.repo_sync_ttl_seconds and os.path.isdir(
                os.path.join(repo.local_path, ".git")
            ):
                return repo.local_path

        repo_dir = self._repo_dir(repo)
        branch = repo.default_branch or "main"

        clone_url = repo.repo_url
        if repo.token_name:
            try:
                token_value = await token_manager.get_token_value(repo.token_name)
            except Exception as exc:
                logger.warning("Token lookup failed for repo %s: %s", repo.name, exc)
                token_value = None
            if token_value:
                clone_url = clone_url.replace("https://", f"https://{token_value}@")

        repo.status = CodeRepositoryStatus.SYNCING
        repo.last_error = None
        await self._save(repo)

        if os.path.isdir(os.path.join(repo_dir, ".git")):
            cmd = (
                f"git -C {shlex.quote(repo_dir)} fetch --depth 1 origin "
                f"{shlex.quote(branch)} && "
                f"git -C {shlex.quote(repo_dir)} checkout FETCH_HEAD"
            )
        else:
            os.makedirs(repo_dir, exist_ok=True)
            cmd = (
                f"git clone --depth 1 --branch {shlex.quote(branch)} "
                f"{shlex.quote(clone_url)} {shlex.quote(repo_dir)}"
            )

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            repo.status = CodeRepositoryStatus.ERROR
            repo.last_error = (stderr.decode(errors="replace") or "git failed")[:500]
            await self._save(repo)
            logger.warning("Repo sync failed for %s: %s", repo.repo_url, repo.last_error)
            return None

        # Capture commit SHA
        sha_proc = await asyncio.create_subprocess_shell(
            f"git -C {shlex.quote(repo_dir)} rev-parse HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        sha_out, _ = await sha_proc.communicate()
        last_sha = sha_out.decode().strip() if sha_proc.returncode == 0 else None

        repo.local_path = repo_dir
        repo.last_commit_sha = last_sha or repo.last_commit_sha
        repo.last_synced_at = datetime.now(UTC)
        repo.status = CodeRepositoryStatus.SYNCED
        await self._save(repo)
        return repo_dir

    # ── Index ─────────────────────────────────────────────────────────────

    async def index(self, repo: CodeRepository) -> dict:
        """Trigger GitNexus to index the synced repo.

        GitNexus mounts repos_data at /workspace, so translate the local path.
        Returns immediately after queuing the job (status → INDEXING).
        """
        if not repo.local_path or not os.path.isdir(repo.local_path):
            return {"indexed": False, "reason": "not_synced"}

        if not settings.gitnexus_url:
            return {"indexed": False, "reason": "gitnexus_unavailable"}

        # Translate /repos/<hash> → /workspace/<hash> (GitNexus volume mount)
        repo_hash = os.path.basename(repo.local_path)
        gitnexus_path = f"/workspace/{repo_hash}"

        repo.status = CodeRepositoryStatus.INDEXING
        repo.last_error = None
        await self._save(repo)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.gitnexus_url.rstrip('/')}/api/analyze",
                    json={"path": gitnexus_path},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            repo.status = CodeRepositoryStatus.ERROR
            repo.last_error = str(exc)[:500]
            await self._save(repo)
            return {"indexed": False, "reason": "gitnexus_error", "error": str(exc)[:500]}

        job_id = data.get("jobId") or data.get("id")
        repo.gitnexus_job_id = job_id
        await self._save(repo)
        return {"indexed": True, "reason": "indexing_started", "gitnexus_job_id": job_id}

    # ── Check index status ────────────────────────────────────────────────

    async def check_index_status(self, repo: CodeRepository) -> dict:
        """Poll GitNexus for the current indexing job status and update the repo.

        Returns a dict with keys: status, gitnexus_status, error (optional).
        """
        if not repo.gitnexus_job_id:
            return {"status": repo.status, "gitnexus_status": None}

        if not settings.gitnexus_url:
            return {"status": repo.status, "gitnexus_status": None}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.gitnexus_url.rstrip('/')}/api/analyze/{repo.gitnexus_job_id}",
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("GitNexus status check failed for %s: %s", repo.name, exc)
            return {"status": repo.status, "gitnexus_status": "unknown", "error": str(exc)[:200]}

        gitnexus_status = data.get("status", "unknown")
        if gitnexus_status == "complete":
            repo.status = CodeRepositoryStatus.INDEXED
            repo.last_indexed_at = datetime.now(UTC)
            repo.gitnexus_job_id = None
            await self._save(repo)
        elif gitnexus_status == "failed":
            repo.status = CodeRepositoryStatus.ERROR
            repo.last_error = data.get("error", "GitNexus indexing failed")[:500]
            repo.gitnexus_job_id = None
            await self._save(repo)

        return {"status": repo.status, "gitnexus_status": gitnexus_status}

    # ── Search ────────────────────────────────────────────────────────────

    async def search(
        self,
        repos: list[CodeRepository],
        query: str,
        limit: int | None = None,
    ) -> list[dict]:
        """Code search is now handled by the GitNexus MCP server (query tool).

        This stub is kept for backward compatibility but always returns empty.
        Use the gitnexus MCP server attached to your agent instead.
        """
        return []

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete(self, repo: CodeRepository) -> None:
        """Remove local checkout."""
        if repo.local_path and os.path.isdir(repo.local_path):
            try:
                shutil.rmtree(repo.local_path, ignore_errors=True)
            except Exception as exc:
                logger.warning("Failed to remove repo dir %s: %s", repo.local_path, exc)

    # ── Workflow resolution ──────────────────────────────────────────────

    async def resolve_for_workflow(self, workflow: Workflow) -> list[CodeRepository]:
        """Return all repos attached to *workflow* via id or tag (deduped)."""
        ids = list(getattr(workflow, "repository_ids", None) or [])
        tags = list(getattr(workflow, "repository_tags", None) or [])
        if not ids and not tags:
            return []

        results: dict[str, CodeRepository] = {}

        if ids:
            from beanie import PydanticObjectId
            for rid in ids:
                try:
                    repo = await CodeRepository.get(PydanticObjectId(rid))
                except Exception:
                    repo = None
                if repo is not None:
                    results[str(repo.id)] = repo

        if tags:
            try:
                tag_repos = await CodeRepository.find(
                    {"tags": {"$in": tags}}
                ).to_list()
            except Exception as exc:
                logger.debug("Tag lookup for repos failed: %s", exc)
                tag_repos = []
            for repo in tag_repos:
                results.setdefault(str(repo.id), repo)

        return list(results.values())

    # ── Internal ─────────────────────────────────────────────────────────

    async def _save(self, repo: CodeRepository) -> None:
        repo.updated_at = datetime.now(UTC)
        try:
            await repo.save()
        except Exception as exc:
            # In tests / when not bound to a DB, .save() may not be possible —
            # fail soft so the manager remains usable in unit tests.
            logger.debug("CodeRepository save skipped: %s", exc)


code_repository_manager = CodeRepositoryManager()
