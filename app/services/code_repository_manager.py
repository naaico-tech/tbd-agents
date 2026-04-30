"""CodeRepositoryManager: clone/sync, index, and semantic search for git repos.

Mirrors the responsibilities of ``KnowledgeManager`` for vector-DB knowledge
sources but applied to git checkouts.  Repos are cached on disk by a
deterministic hash of ``url+branch`` so multiple workflows can share a single
checkout.  Each repo gets its own Qdrant collection.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shlex
import shutil
import uuid
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import settings
from app.models.code_repository import CodeRepository, CodeRepositoryStatus
from app.services import token_manager
from app.services.embeddings import embeddings_service

if TYPE_CHECKING:
    from app.models.workflow import Workflow

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _chunk_text(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    """Split *text* into overlapping character-based chunks.

    Mirrors ``app.services.knowledge_manager._chunk_text``.
    """
    if chunk_chars <= 0:
        return [text] if text else []
    if len(text) <= chunk_chars:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += max(1, chunk_chars - overlap_chars)
    return [c for c in chunks if c.strip()]


def _collection_name(repo_url: str, branch: str) -> str:
    digest = hashlib.sha256(f"{repo_url}:{branch}".encode()).hexdigest()[:16]
    return f"code_{digest}"


def _matches_any(rel_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch(rel_path, pat):
            return True
        # Match basename for plain "*.py"-style patterns when path has dirs
        if "/" not in pat and fnmatch(os.path.basename(rel_path), pat):
            return True
    return False


def _line_range_for_chunk(text: str, chunk: str) -> tuple[int, int]:
    """Return (line_start, line_end) (1-indexed) of *chunk* inside *text*.

    Falls back to (1, line_count(chunk)) if the chunk cannot be located.
    """
    idx = text.find(chunk)
    if idx < 0:
        n = chunk.count("\n") + 1
        return 1, n
    line_start = text.count("\n", 0, idx) + 1
    line_end = line_start + chunk.count("\n")
    return line_start, line_end


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
        if not repo.vector_collection:
            repo.vector_collection = _collection_name(repo.repo_url, branch)
        await self._save(repo)
        return repo_dir

    # ── Index ─────────────────────────────────────────────────────────────

    async def index(self, repo: CodeRepository) -> dict:
        """Walk the synced repo, chunk text, embed, and upsert to Qdrant.

        Always recreates the collection (full re-index).
        """
        if not repo.local_path or not os.path.isdir(repo.local_path):
            return {"indexed": False, "reason": "not_synced"}

        if not settings.embeddings_enabled:
            repo.status = CodeRepositoryStatus.SYNCED
            await self._save(repo)
            return {"indexed": False, "reason": "embeddings_unavailable"}

        repo.status = CodeRepositoryStatus.INDEXING
        repo.last_error = None
        await self._save(repo)

        cfg = repo.indexing
        root = Path(repo.local_path)
        include_globs = cfg.include_globs or []
        exclude_globs = cfg.exclude_globs or []
        max_bytes = max(0, int(cfg.max_file_kb)) * 1024

        # ── Walk + chunk ──────────────────────────────────────────────────
        chunks_payload: list[dict] = []
        file_count = 0
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                rel = file_path.relative_to(root).as_posix()
            except ValueError:
                continue
            if _matches_any(rel, exclude_globs):
                continue
            if include_globs and not _matches_any(rel, include_globs):
                continue
            try:
                if max_bytes and file_path.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not text.strip():
                continue
            file_chunks = _chunk_text(text, cfg.chunk_chars, cfg.overlap_chars)
            if not file_chunks:
                continue
            file_count += 1
            total = len(file_chunks)
            for idx, chunk in enumerate(file_chunks):
                line_start, line_end = _line_range_for_chunk(text, chunk)
                chunks_payload.append({
                    "file_path": rel,
                    "chunk_index": idx,
                    "chunk_total": total,
                    "line_start": line_start,
                    "line_end": line_end,
                    "text": chunk,
                })

        if not chunks_payload:
            repo.file_count = 0
            repo.chunk_count = 0
            repo.status = CodeRepositoryStatus.INDEXED
            repo.last_indexed_at = datetime.now(UTC)
            await self._save(repo)
            return {"indexed": True, "file_count": 0, "chunk_count": 0}

        # ── Embed in batches ──────────────────────────────────────────────
        all_vectors: list[list[float]] = []
        batch_size = 32
        texts = [c["text"] for c in chunks_payload]
        for i in range(0, len(texts), batch_size):
            vecs = await embeddings_service.embed_many(texts[i:i + batch_size])
            if vecs is None:
                repo.status = CodeRepositoryStatus.SYNCED
                await self._save(repo)
                return {"indexed": False, "reason": "embeddings_unavailable"}
            all_vectors.extend(vecs)

        # ── Upsert to Qdrant ──────────────────────────────────────────────
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.http import models as qmodels

        branch = repo.default_branch or "main"
        collection = repo.vector_collection or _collection_name(repo.repo_url, branch)
        repo.vector_collection = collection

        client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        try:
            try:
                await client.delete_collection(collection_name=collection)
            except Exception:
                pass
            await client.create_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(
                    size=settings.embeddings_dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )

            points = []
            for payload, vector in zip(chunks_payload, all_vectors, strict=False):
                points.append(qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "repo_id": str(repo.id),
                        "repo_name": repo.name,
                        **payload,
                    },
                ))
            # Upsert in chunks to be safe
            for i in range(0, len(points), 256):
                await client.upsert(collection_name=collection, points=points[i:i + 256])
        except Exception as exc:
            logger.warning("Qdrant indexing failed for %s: %s", repo.name, exc)
            repo.status = CodeRepositoryStatus.ERROR
            repo.last_error = str(exc)[:500]
            await self._save(repo)
            return {"indexed": False, "reason": "qdrant_error", "error": str(exc)[:500]}
        finally:
            try:
                await client.close()
            except Exception:
                pass

        repo.file_count = file_count
        repo.chunk_count = len(chunks_payload)
        repo.last_indexed_at = datetime.now(UTC)
        repo.status = CodeRepositoryStatus.INDEXED
        await self._save(repo)
        return {
            "indexed": True,
            "file_count": file_count,
            "chunk_count": len(chunks_payload),
        }

    # ── Search ────────────────────────────────────────────────────────────

    async def search(
        self,
        repos: list[CodeRepository],
        query: str,
        limit: int | None = None,
    ) -> list[dict]:
        """Embed *query* and search across each repo's collection."""
        if not repos or not query:
            return []
        if not settings.embeddings_enabled:
            return []
        effective_limit = limit or settings.code_search_top_k
        query_vec = await embeddings_service.embed_one(query)
        if query_vec is None:
            return []

        from qdrant_client import AsyncQdrantClient

        client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        merged: list[dict] = []
        try:
            for repo in repos:
                if not repo.vector_collection:
                    continue
                try:
                    results = await client.query_points(
                        collection_name=repo.vector_collection,
                        query=query_vec,
                        limit=effective_limit,
                        with_payload=True,
                    )
                except Exception as exc:
                    logger.debug("code_search miss for %s: %s", repo.name, exc)
                    continue
                for point in results.points:
                    payload = point.payload or {}
                    merged.append({
                        "repo_id": payload.get("repo_id") or str(repo.id),
                        "repo_name": payload.get("repo_name") or repo.name,
                        "file_path": payload.get("file_path", ""),
                        "line_start": int(payload.get("line_start", 1)),
                        "line_end": int(payload.get("line_end", 1)),
                        "score": float(point.score or 0.0),
                        "text": payload.get("text", ""),
                    })
        finally:
            try:
                await client.close()
            except Exception:
                pass

        merged.sort(key=lambda r: r["score"], reverse=True)
        return merged[:effective_limit]

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete(self, repo: CodeRepository) -> None:
        """Best-effort: remove local checkout + drop Qdrant collection."""
        if repo.local_path and os.path.isdir(repo.local_path):
            try:
                shutil.rmtree(repo.local_path, ignore_errors=True)
            except Exception as exc:
                logger.warning("Failed to remove repo dir %s: %s", repo.local_path, exc)
        if repo.vector_collection and settings.qdrant_url:
            try:
                from qdrant_client import AsyncQdrantClient

                client = AsyncQdrantClient(
                    url=settings.qdrant_url, api_key=settings.qdrant_api_key
                )
                try:
                    await client.delete_collection(collection_name=repo.vector_collection)
                finally:
                    await client.close()
            except Exception as exc:
                logger.debug(
                    "Qdrant collection drop failed for %s: %s",
                    repo.vector_collection, exc,
                )

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
