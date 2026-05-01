"""CodeRepositoryManager: clone/sync, index, and search for git repos.

Mirrors the responsibilities of ``KnowledgeManager`` for knowledge sources but
applied to git checkouts.  Repos are cached on disk under a sanitised name
derived from the repository name + a short URL hash so directories are both
human-readable and collision-safe.  Indexing uses an internal Qdrant pipeline
(discover_changes → index_changes) with the GitNexus MCP server used for code
search queries.
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import httpx
import logging
import math
import os
import re
import shlex
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

from app.config import settings
from app.models.code_repository import CodeRepository, CodeRepositoryStatus
from app.models.indexed_file import IndexedFile
from app.services import index_progress, token_manager
from app.services.embeddings import embeddings_service

if TYPE_CHECKING:
    from app.models.workflow import Workflow

logger = logging.getLogger(__name__)

# ── Indexing constants ────────────────────────────────────────────────────────

# Stable UUID namespace for deterministic Qdrant point IDs.  Never change this
# value — doing so would invalidate every persisted point id across all repos.
NS_REPO = UUID("6e0c1c4e-7c85-4f4c-9f3a-1f4c4a1f4c4a")

EMBED_BATCH_SIZE: int = int(os.environ.get("INDEX_EMBED_BATCH_SIZE", "128"))


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class FileChange:
    """A single file change produced by :func:`discover_changes`."""

    path: str
    blob_sha: str
    change: str  # "added" | "modified" | "deleted"
    size: int


@dataclass
class Manifest:
    """Summary of changes between two git commits (or a full first-time scan)."""

    head_sha: str
    base_sha: str | None
    changes: list[FileChange] = field(default_factory=list)


# ── Deterministic point ID ────────────────────────────────────────────────────


def _point_id(repo_id: str, path: str, chunk_idx: int, blob_sha: str) -> str:
    """Return a stable UUIDv5 string for a given (repo, path, chunk, blob) tuple.

    IDs are deterministic so re-indexing a file produces the same Qdrant point
    ids and upserts are idempotent across retries.
    """
    key = f"{repo_id}:{path}:{chunk_idx}:{blob_sha}"
    return str(uuid5(NS_REPO, key))


# ── Qdrant collection helpers ─────────────────────────────────────────────────


async def _ensure_collection(client: Any, collection_name: str, dim: int) -> None:
    """Create *collection_name* with cosine distance if it does not yet exist.

    Two payload indexes (``repo_id`` and ``file_path``) are created best-effort
    so the collection is already set up for filtered queries.  Errors on index
    creation are swallowed — Qdrant will function without them.
    """
    exists = await client.collection_exists(collection_name)
    if not exists:
        from qdrant_client.models import Distance, VectorParams

        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    # Payload indexes — best-effort (may already exist on re-index).
    for field_name in ("repo_id", "file_path"):
        try:
            from qdrant_client.models import PayloadSchemaType

            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


# ── IndexedFile helpers ───────────────────────────────────────────────────────

# These thin wrappers are module-level so tests can monkeypatch them easily.


async def _find_indexed_file(repo_id: str, file_path: str) -> Any:
    try:
        return await IndexedFile.find_one(
            {"repo_id": repo_id, "file_path": file_path}
        )
    except Exception:
        return None


async def _upsert_indexed_file(
    *,
    repo_id: str,
    file_path: str,
    blob_sha: str,
    chunk_ids: list[str],
    n_chunks: int,
    size_bytes: int,
) -> None:
    existing = await _find_indexed_file(str(repo_id), file_path)
    if existing is not None:
        existing.blob_sha = blob_sha
        existing.chunk_ids = list(chunk_ids)
        existing.n_chunks = n_chunks
        existing.size_bytes = size_bytes
        existing.indexed_at = datetime.now(UTC)
        existing.error = None
        await existing.save()
    else:
        doc = IndexedFile(
            repo_id=repo_id,
            file_path=file_path,
            blob_sha=blob_sha,
            chunk_ids=list(chunk_ids),
            n_chunks=n_chunks,
            size_bytes=size_bytes,
        )
        await doc.insert()


async def _record_indexed_file_error(
    repo_id: str, file_path: str, blob_sha: str, error: str
) -> None:
    logger.warning("Index error for %s/%s: %s", repo_id, file_path, error)
    try:
        existing = await _find_indexed_file(str(repo_id), file_path)
        if existing is not None:
            existing.blob_sha = blob_sha
            existing.error = error[:500]
            await existing.save()
        else:
            doc = IndexedFile(
                repo_id=repo_id,
                file_path=file_path,
                blob_sha=blob_sha,
                chunk_ids=[],
                n_chunks=0,
                size_bytes=0,
                error=error[:500],
            )
            await doc.insert()
    except Exception as exc:
        logger.debug("Could not persist error record for %s/%s: %s", repo_id, file_path, exc)


# ── Glob filter ───────────────────────────────────────────────────────────────


def _matches_globs(
    path: str, include: list[str], exclude: list[str]
) -> bool:
    """Return True when *path* passes the include/exclude glob filters."""
    if include and not any(fnmatch.fnmatch(path, g) for g in include):
        return False
    if exclude and any(fnmatch.fnmatch(path, g) for g in exclude):
        return False
    return True


# ── Text chunker ──────────────────────────────────────────────────────────────


def _chunk_text(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    """Split *text* into overlapping fixed-size character chunks.

    Returns a list of non-empty chunk strings.  When the entire text fits in
    one chunk it is returned as-is (no unnecessary copies).
    """
    if not text.strip():
        return []
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_chars - max(0, overlap_chars)
    return [c for c in chunks if c.strip()]


# ── Git helpers ───────────────────────────────────────────────────────────────


async def _git(cwd: str, *args: str) -> tuple[int, str]:
    """Run a git sub-command in *cwd* and return (returncode, stdout)."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", cwd, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace")


def _parse_ls_tree(output: str) -> list[tuple[str, str, int]]:
    """Parse ``git ls-tree -r -l`` output into (path, blob_sha, size) triples.

    The format is: ``<mode> <type> <sha> <size>\\t<path>`` (one TAB before the path).
    """
    results = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Split at the first TAB to separate metadata from path.
        tab_parts = line.split("\t", 1)
        if len(tab_parts) != 2:
            continue
        meta_parts = tab_parts[0].split()
        # Expected: [mode, type, sha, size]
        if len(meta_parts) < 4 or meta_parts[1] != "blob":
            continue
        blob_sha = meta_parts[2]
        try:
            size = int(meta_parts[3])
        except ValueError:
            continue
        path = tab_parts[1].strip()
        results.append((path, blob_sha, size))
    return results


# ── discover_changes ──────────────────────────────────────────────────────────


async def discover_changes(
    repo: Any,
    base_sha: str | None,
    head_sha: str,
) -> Manifest:
    """Build a :class:`Manifest` describing what has changed since *base_sha*.

    When *base_sha* is ``None`` (or the base is unreachable), performs a full
    ``git ls-tree`` scan and marks every matching file as ``added``.  Otherwise
    diffs *base_sha* → *head_sha* to produce incremental add/modify/delete
    entries.

    Applies ``repo.indexing.include_globs``, ``exclude_globs``, and
    ``max_file_kb`` filters.
    """
    if not repo.local_path:
        raise RuntimeError("Repository not synced: local_path is None")

    cwd = repo.local_path
    include = list(repo.indexing.include_globs or [])
    exclude = list(repo.indexing.exclude_globs or [])
    max_bytes = int(repo.indexing.max_file_kb) * 1024

    # ── Incremental diff path ──────────────────────────────────────────────
    if base_sha:
        try:
            changes = await _diff_changes(cwd, base_sha, head_sha, include, exclude, max_bytes)
            return Manifest(head_sha=head_sha, base_sha=base_sha, changes=changes)
        except Exception:
            # Unreachable base (e.g. shallow clone gap, force-push) — fall through
            # to full scan and treat as first-time index.
            base_sha = None

    # ── Full scan (first-time or fallback) ────────────────────────────────
    changes = await _lstree_changes(cwd, head_sha, include, exclude, max_bytes)
    return Manifest(head_sha=head_sha, base_sha=None, changes=changes)


async def _lstree_changes(
    cwd: str,
    head_sha: str,
    include: list[str],
    exclude: list[str],
    max_bytes: int,
) -> list[FileChange]:
    rc, out = await _git(cwd, "ls-tree", "-r", "-l", head_sha)
    if rc != 0:
        return []
    results = []
    for path, blob_sha, size in _parse_ls_tree(out):
        if max_bytes > 0 and size > max_bytes:
            continue
        if not _matches_globs(path, include, exclude):
            continue
        results.append(FileChange(path=path, blob_sha=blob_sha, change="added", size=size))
    return results


async def _diff_changes(
    cwd: str,
    base_sha: str,
    head_sha: str,
    include: list[str],
    exclude: list[str],
    max_bytes: int,
) -> list[FileChange]:
    """Return per-file changes between *base_sha* and *head_sha*."""
    rc, out = await _git(cwd, "diff", "--name-status", base_sha, head_sha)
    if rc != 0:
        raise RuntimeError(f"git diff failed (rc={rc})")

    deletions: list[str] = []
    additions: list[tuple[str, str]] = []  # (path, change_type)

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].strip()[0]  # A, M, D, R, C, …
        path = parts[-1].strip()  # last column = destination path

        if not _matches_globs(path, include, exclude):
            continue
        if status == "D":
            deletions.append(path)
        elif status in ("A", "C"):
            additions.append((path, "added"))
        elif status in ("M", "R"):
            additions.append((path, "modified"))

    changes: list[FileChange] = [
        FileChange(path=p, blob_sha="", change="deleted", size=0)
        for p in deletions
    ]

    if additions:
        add_paths = [p for p, _ in additions]
        add_type_map = {p: t for p, t in additions}
        rc2, out2 = await _git(cwd, "ls-tree", "-l", head_sha, "--", *add_paths)
        sha_size_map: dict[str, tuple[str, int]] = {}
        if rc2 == 0:
            for path, blob_sha, size in _parse_ls_tree(out2):
                sha_size_map[path] = (blob_sha, size)
        for path, change_type in additions:
            blob_sha, size = sha_size_map.get(path, ("", 0))
            if max_bytes > 0 and size > max_bytes:
                continue
            changes.append(
                FileChange(path=path, blob_sha=blob_sha, change=change_type, size=size)
            )

    return changes


# ── Manager ──────────────────────────────────────────────────────────────────


class CodeRepositoryManager:
    """Sync, index, and search code repositories."""

    # ── Path helpers ──────────────────────────────────────────────────────

    def _repo_dir(self, repo: CodeRepository) -> str:
        """Return a stable, human-readable local path for *repo*.

        Uses ``<sanitised-name>-<8-char-url-hash>`` so directories are both
        recognisable and collision-safe across repos with the same name.
        """
        branch = repo.default_branch or "main"
        digest = hashlib.sha256(
            f"{repo.repo_url}:{branch}".encode()
        ).hexdigest()[:8]
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", repo.name)
        return os.path.join(settings.repos_base, f"{safe_name}-{digest}")

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

    # ── Index (compat shim → internal pipeline) ───────────────────────────

    async def index(self, repo: CodeRepository) -> dict:
        """Compat shim: index *repo* via GitNexus when configured, otherwise run
        the embedding pipeline directly (discover → index_changes).

        Returns a dict with ``indexed`` boolean and contextual keys so existing
        call-sites keep working without modification.
        """
        if not repo.local_path:
            return {"indexed": False, "reason": "not_synced"}

        if settings.gitnexus_url:
            # GitNexus path: submit the repo for external analysis.
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.gitnexus_url}/api/analyze",
                    json={"repo_path": repo.local_path, "repo_id": str(repo.id)},
                )
                resp.raise_for_status()
                data = resp.json()

            job_id = data.get("jobId")
            repo.status = CodeRepositoryStatus.INDEXING
            repo.gitnexus_job_id = job_id
            return {"indexed": True, "gitnexus_job_id": job_id, "reason": "indexing_started"}

        # No GitNexus — run the embedding pipeline inline.
        head_sha = repo.last_commit_sha or ""
        if not head_sha and os.path.isdir(repo.local_path):
            rc, out = await _git(repo.local_path, "rev-parse", "HEAD")
            if rc == 0:
                head_sha = out.strip()
                repo.last_commit_sha = head_sha

        manifest = await discover_changes(repo, None, head_sha)
        result = await self.index_changes(repo, manifest)
        result.setdefault("file_count", getattr(repo, "file_count", 0))
        result.setdefault("chunk_count", getattr(repo, "chunk_count", 0))
        return result

    # ── index_changes ─────────────────────────────────────────────────────

    async def index_changes(
        self,
        repo: Any,
        manifest: Manifest,
        *,
        job_id: str | None = None,
        finalize: bool = True,
    ) -> dict:
        """Embed and upsert all changes described by *manifest*.

        Chunks are streamed through a cross-file buffer of size
        ``EMBED_BATCH_SIZE`` so memory usage is bounded regardless of repo
        size.  Qdrant updates use deterministic point IDs making individual
        files idempotent under retry.

        When *job_id* is given, progress counters are updated in Redis via the
        sync helpers so the SSE stream stays current.

        When *finalize* is ``False`` (shard workers) the call returns without
        touching ``CodeRepository`` summary fields — the chord callback handles
        that exactly once via :meth:`finalize_repo`.
        """
        counters: dict[str, Any] = {
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "chunks_done": 0,
            "files_failed": 0,
        }

        # Fast-path: nothing to do
        if not manifest.changes:
            repo.last_commit_sha = manifest.head_sha
            if finalize:
                repo.status = CodeRepositoryStatus.INDEXED
                await self._save(repo)
            return {"indexed": True, **counters}

        # ── Qdrant client ──────────────────────────────────────────────────
        collection = getattr(repo, "vector_collection", None) or f"code_{repo.id}"
        dim = settings.embeddings_dim
        qdrant = None
        if settings.qdrant_url:
            try:
                from qdrant_client import AsyncQdrantClient

                qdrant = AsyncQdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                )
                await _ensure_collection(qdrant, collection, dim)
            except Exception as exc:
                logger.warning("Qdrant unavailable — skipping vector upserts: %s", exc)
                qdrant = None

        # ── Streaming batch state ──────────────────────────────────────────
        buf_texts: list[str] = []
        buf_pids: list[str] = []
        buf_payloads: list[dict] = []
        # Global chunk-stream position (incremented as chunks are added to buf)
        total_chunks_added = 0
        # How many chunks have been flushed (embedded + upserted) so far
        chunks_flushed = 0
        # Per-file record: written after ALL its chunks are flushed
        pending_files: list[dict] = []

        async def _flush() -> None:
            nonlocal chunks_flushed
            if not buf_texts:
                return

            n = len(buf_texts)
            # Embed
            vecs = await embeddings_service.embed_many(list(buf_texts))

            # Upsert to Qdrant
            if qdrant is not None:
                from qdrant_client.models import PointStruct

                points = [
                    PointStruct(id=pid, vector=vec, payload=payload)
                    for pid, vec, payload in zip(buf_pids, vecs, buf_payloads)
                ]
                await qdrant.upsert(collection_name=collection, points=points)

            # Update progress counters
            counters["chunks_done"] += n
            if job_id:
                index_progress.incr_sync(job_id, chunks_done=n)

            chunks_flushed += n
            buf_texts.clear()
            buf_pids.clear()
            buf_payloads.clear()

            # Write IndexedFile rows for files whose last chunk is now flushed
            for pf in pending_files:
                if not pf["written"] and pf["end_idx"] <= chunks_flushed:
                    try:
                        await _upsert_indexed_file(
                            repo_id=str(repo.id),
                            file_path=pf["path"],
                            blob_sha=pf["blob_sha"],
                            chunk_ids=pf["chunk_ids"],
                            n_chunks=pf["n_chunks"],
                            size_bytes=pf["size"],
                        )
                    except Exception as exc:
                        logger.warning(
                            "IndexedFile upsert failed for %s: %s", pf["path"], exc
                        )
                    pf["written"] = True

        # ── Process each file change ───────────────────────────────────────
        cancelled = False
        for change in manifest.changes:
            # ── Deleted ───────────────────────────────────────────────────
            if change.change == "deleted":
                old = await _find_indexed_file(str(repo.id), change.path)
                if old is not None:
                    if qdrant is not None and old.chunk_ids:
                        from qdrant_client.models import PointIdsList

                        await qdrant.delete(
                            collection_name=collection,
                            points_selector=PointIdsList(points=old.chunk_ids),
                        )
                    await old.delete()
                counters["deleted"] += 1
                continue

            # ── Modified: delete stale vectors first ──────────────────────
            if change.change == "modified":
                old = await _find_indexed_file(str(repo.id), change.path)
                if old is not None and qdrant is not None and old.chunk_ids:
                    from qdrant_client.models import PointIdsList

                    await qdrant.delete(
                        collection_name=collection,
                        points_selector=PointIdsList(points=old.chunk_ids),
                    )
                counters["modified"] += 1
            else:
                counters["added"] += 1

            # ── Read + chunk ───────────────────────────────────────────────
            if repo.local_path:
                file_path = os.path.join(repo.local_path, change.path)
            else:
                file_path = change.path
            try:
                with open(file_path, encoding="utf-8") as fh:
                    text = fh.read()
            except Exception as exc:
                await _record_indexed_file_error(
                    str(repo.id), change.path, change.blob_sha, str(exc)[:400]
                )
                counters["files_failed"] += 1
                if change.change != "modified":
                    counters["added"] -= 1
                else:
                    counters["modified"] -= 1
                continue

            cfg = repo.indexing
            chunks = _chunk_text(text, cfg.chunk_chars, cfg.overlap_chars)
            if not chunks:
                # Empty / whitespace file — record as indexed with 0 chunks.
                await _upsert_indexed_file(
                    repo_id=str(repo.id),
                    file_path=change.path,
                    blob_sha=change.blob_sha,
                    chunk_ids=[],
                    n_chunks=0,
                    size_bytes=len(text.encode()),
                )
                continue

            # Compute all point IDs for this file upfront so we can record
            # the complete list on the IndexedFile row.
            chunk_ids_for_file = [
                _point_id(str(repo.id), change.path, i, change.blob_sha)
                for i in range(len(chunks))
            ]
            file_start_idx = total_chunks_added

            # Feed chunks into the cross-file buffer, flushing when full.
            file_cancelled = False
            for i, chunk in enumerate(chunks):
                pid = chunk_ids_for_file[i]
                buf_texts.append(chunk)
                buf_pids.append(pid)
                buf_payloads.append(
                    {
                        "repo_id": str(repo.id),
                        "file_path": change.path,
                        "chunk_index": i,
                        "blob_sha": change.blob_sha,
                    }
                )
                total_chunks_added += 1

                if len(buf_texts) >= EMBED_BATCH_SIZE:
                    await _flush()
                    # Check cancellation between batches
                    if job_id and index_progress.is_cancelled_sync(job_id):
                        file_cancelled = True
                        cancelled = True
                        break

            if file_cancelled:
                break

            # Register this file for IndexedFile row creation after its last
            # chunk is flushed.
            pending_files.append(
                {
                    "path": change.path,
                    "blob_sha": change.blob_sha,
                    "size": len(text.encode()),
                    "chunk_ids": chunk_ids_for_file,
                    "n_chunks": len(chunks),
                    "end_idx": total_chunks_added,
                    "written": False,
                }
            )

        # ── Flush remaining buffer (if not cancelled mid-file) ─────────────
        if not cancelled:
            await _flush()

        # ── Finalise repo state ────────────────────────────────────────────
        repo.last_commit_sha = manifest.head_sha
        if finalize:
            repo.status = CodeRepositoryStatus.INDEXED
            await self._save(repo)

        if qdrant is not None:
            try:
                await qdrant.close()
            except Exception:
                pass

        return {"indexed": True, **counters}

    # ── finalize_repo ─────────────────────────────────────────────────────

    async def finalize_repo(self, repo: Any, head_sha: str) -> dict:
        """Recompute and persist ``file_count``, ``chunk_count``, etc.

        Called exactly once per index job by the chord callback so summary
        fields are never subject to shard races.
        """
        try:
            file_count = await IndexedFile.find(
                {"repo_id": str(repo.id)}
            ).count()
            chunk_count = 0
            async for doc in IndexedFile.find({"repo_id": str(repo.id)}):
                chunk_count += doc.n_chunks
        except Exception as exc:
            logger.warning("finalize_repo: IndexedFile query failed: %s", exc)
            file_count = getattr(repo, "file_count", 0)
            chunk_count = getattr(repo, "chunk_count", 0)

        repo.file_count = file_count
        repo.chunk_count = chunk_count
        repo.last_commit_sha = head_sha or repo.last_commit_sha
        repo.last_indexed_at = datetime.now(UTC)
        repo.status = CodeRepositoryStatus.INDEXED
        await self._save(repo)
        return {
            "file_count": file_count,
            "chunk_count": chunk_count,
            "last_commit_sha": head_sha,
        }

    # ── Check index status (GitNexus) ─────────────────────────────────────

    async def check_index_status(self, repo: CodeRepository) -> dict:
        """Poll GitNexus for the current indexing job status and update the repo."""
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

    async def _save(self, repo: Any) -> None:
        repo.updated_at = datetime.now(UTC)
        try:
            await repo.save()
        except Exception as exc:
            # In tests / when not bound to a DB, .save() may not be possible —
            # fail soft so the manager remains usable in unit tests.
            logger.debug("CodeRepository save skipped: %s", exc)


code_repository_manager = CodeRepositoryManager()
