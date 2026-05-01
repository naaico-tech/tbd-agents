"""REST API for the CodeRepository library."""

import asyncio
import json
import logging
from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.models.code_repository import (
    CodeRepository,
    CodeRepositoryStatus,
)
from app.models.index_job import TERMINAL_STATES, IndexJob
from app.schemas.code_repository import (
    CodeRepositoryCreate,
    CodeRepositoryIndexResponse,
    CodeRepositoryResponse,
    CodeRepositorySyncResponse,
    CodeRepositoryUpdate,
    IndexJobDetailResponse,
    IndexJobEnqueueResponse,
    IndexJobSummaryResponse,
)
from app.schemas.export_import import (
    CodeRepositoryExportBundle,
    CodeRepositoryImportBundle,
    ExportedCodeRepository,
    ImportResult,
)
from app.services import index_progress
from app.services.code_repository_manager import code_repository_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/code-repositories", tags=["code-repositories"])


def _to_response(repo: CodeRepository) -> CodeRepositoryResponse:
    return CodeRepositoryResponse(
        id=str(repo.id),
        name=repo.name,
        description=repo.description,
        repo_url=repo.repo_url,
        default_branch=repo.default_branch,
        token_name=repo.token_name,
        tags=repo.tags,
        status=repo.status,
        last_synced_at=repo.last_synced_at,
        last_indexed_at=repo.last_indexed_at,
        last_commit_sha=repo.last_commit_sha,
        last_error=repo.last_error,
        local_path=repo.local_path,
        file_count=repo.file_count,
        gitnexus_job_id=repo.gitnexus_job_id,
        github_user=repo.github_user,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


def _to_exported(repo: CodeRepository) -> ExportedCodeRepository:
    return ExportedCodeRepository(
        name=repo.name,
        description=repo.description,
        repo_url=repo.repo_url,
        default_branch=repo.default_branch,
        token_name=repo.token_name,
        tags=repo.tags,
    )


def _require_owner(repo: CodeRepository, user: dict) -> None:
    if repo.github_user and repo.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your code repository")


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=CodeRepositoryResponse, status_code=201)
async def create_code_repository(
    body: CodeRepositoryCreate, user=Depends(get_current_user)
):
    repo = CodeRepository(
        name=body.name,
        description=body.description,
        repo_url=body.repo_url,
        default_branch=body.default_branch,
        token_name=body.token_name,
        tags=body.tags,
        github_user=user["login"],
    )
    await repo.insert()
    return _to_response(repo)


@router.get("", response_model=list[CodeRepositoryResponse])
async def list_code_repositories(
    tags: str | None = None, _user=Depends(get_current_user)
):
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        repos = await CodeRepository.find({"tags": {"$in": tag_list}}).to_list()
    else:
        repos = await CodeRepository.find_all().to_list()
    return [_to_response(r) for r in repos]


# ── Export / Import ──────────────────────────────────────────────────────────


@router.get("/export", response_model=CodeRepositoryExportBundle)
async def export_code_repositories(_user=Depends(get_current_user)):
    repos = await CodeRepository.find_all().to_list()
    return CodeRepositoryExportBundle(items=[_to_exported(r) for r in repos])


@router.get("/{repo_id}/export", response_model=CodeRepositoryExportBundle)
async def export_code_repository(repo_id: str, _user=Depends(get_current_user)):
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    return CodeRepositoryExportBundle(items=[_to_exported(repo)])


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_code_repositories(
    body: CodeRepositoryImportBundle, user=Depends(get_current_user)
):
    result = ImportResult()
    for item in body.items:
        try:
            repo = CodeRepository(
                name=item.name,
                description=item.description,
                repo_url=item.repo_url,
                default_branch=item.default_branch,
                token_name=item.token_name,
                tags=item.tags,
                github_user=user["login"],
            )
            await repo.insert()
            result.ids.append(str(repo.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


# ── Single resource ──────────────────────────────────────────────────────────


@router.get("/{repo_id}", response_model=CodeRepositoryResponse)
async def get_code_repository(repo_id: str, _user=Depends(get_current_user)):
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    return _to_response(repo)


@router.put("/{repo_id}", response_model=CodeRepositoryResponse)
async def update_code_repository(
    repo_id: str, body: CodeRepositoryUpdate, user=Depends(get_current_user)
):
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(repo, k, v)
    repo.updated_at = datetime.now(UTC)
    await repo.save()
    return _to_response(repo)


@router.delete("/{repo_id}", status_code=204)
async def delete_code_repository(repo_id: str, user=Depends(get_current_user)):
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)
    await code_repository_manager.delete(repo)
    await repo.delete()
    return None


# ── Lifecycle: sync ───────────────────────────────────────────────────────────


@router.post("/{repo_id}/sync", response_model=CodeRepositorySyncResponse)
async def sync_code_repository(repo_id: str, user=Depends(get_current_user)):
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)
    await code_repository_manager.sync(repo, force=True)
    return CodeRepositorySyncResponse(
        status=repo.status,
        local_path=repo.local_path,
        last_commit_sha=repo.last_commit_sha,
        last_error=repo.last_error,
    )


# ── Index: enqueue via Celery ─────────────────────────────────────────────────


@router.post(
    "/{repo_id}/index",
    response_model=IndexJobEnqueueResponse,
    status_code=202,
)
async def index_code_repository(
    repo_id: str,
    force: bool = False,
    user=Depends(get_current_user),
):
    """Enqueue an indexing job for the repository.

    Returns 202 immediately.  If an in-progress job already exists the same
    job is returned with ``idempotent=True`` and the Celery task is NOT
    re-queued.
    """
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)

    # Idempotency: return existing in-progress job without double-queuing.
    existing = await IndexJob.find_one(
        {"repo_id": PydanticObjectId(repo_id), "state": {"$nin": list(TERMINAL_STATES)}}
    )
    if existing:
        return IndexJobEnqueueResponse(
            job_id=str(existing.id),
            state=existing.state,
            idempotent=True,
        )

    job = IndexJob(repo_id=PydanticObjectId(repo_id))
    await job.insert()

    from app.tasks.index_repository_task import run_index_repository_job

    run_index_repository_job.delay(str(job.id), force)

    return IndexJobEnqueueResponse(
        job_id=str(job.id),
        state=job.state,
        idempotent=False,
    )


@router.get("/{repo_id}/index/status", response_model=CodeRepositoryIndexResponse)
async def get_index_status(repo_id: str, user=Depends(get_current_user)):
    """Poll GitNexus for the current indexing job status and update the repo record."""
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)
    await code_repository_manager.check_index_status(repo)
    return CodeRepositoryIndexResponse(
        status=repo.status,
        indexed=repo.status == CodeRepositoryStatus.INDEXED,
        file_count=repo.file_count,
        gitnexus_job_id=repo.gitnexus_job_id,
        reason=None,
        last_error=repo.last_error,
    )


# ── Job sub-resources ─────────────────────────────────────────────────────────


@router.get("/{repo_id}/jobs", response_model=list[IndexJobSummaryResponse])
async def list_index_jobs(repo_id: str, _user=Depends(get_current_user)):
    """List index jobs for a repository (newest first, max 20)."""
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")

    jobs = (
        await IndexJob.find({"repo_id": PydanticObjectId(repo_id)})
        .sort(-IndexJob.created_at)
        .limit(20)
        .to_list()
    )
    return [
        IndexJobSummaryResponse(
            id=str(j.id),
            repo_id=str(j.repo_id),
            state=j.state,
            kind=j.kind,
            shard_count=j.shard_count,
            shards_done=j.shards_done,
            head_commit_sha=j.head_commit_sha,
            base_commit_sha=j.base_commit_sha,
            started_at=j.started_at,
            finished_at=j.finished_at,
            created_at=j.created_at,
            updated_at=j.updated_at,
        )
        for j in jobs
    ]


@router.get("/{repo_id}/jobs/{job_id}", response_model=IndexJobDetailResponse)
async def get_index_job(
    repo_id: str, job_id: str, _user=Depends(get_current_user)
):
    """Get index job detail, overlaying live Redis counters."""
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")

    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job or str(job.repo_id) != repo_id:
        raise HTTPException(status_code=404, detail="Index job not found")

    # Overlay Redis progress counters
    snap = await index_progress.snapshot(job_id)
    base_counters = job.counters.model_dump() if hasattr(job.counters, "model_dump") else {}

    chunks_total = int(snap.get("chunks_total") or base_counters.get("chunks_total") or 0)
    chunks_done = int(snap.get("chunks_done") or base_counters.get("chunks_done") or 0)
    files_done = int(snap.get("files_done") or base_counters.get("files_done") or 0)

    merged_counters = {**base_counters}
    if snap:
        for k in ("files_total", "files_done", "files_failed", "chunks_total", "chunks_done", "bytes_done"):
            if k in snap:
                merged_counters[k] = int(snap[k])

    progress_pct = (chunks_done / chunks_total * 100.0) if chunks_total else 0.0
    is_terminal = job.state in TERMINAL_STATES

    # Redis overlay for current_phase / current_file
    current_phase = snap.get("phase") or snap.get("current_phase") or job.current_phase or job.state
    current_file = snap.get("current_file") or job.current_file

    error_dict = None
    if job.error:
        error_dict = (
            job.error.model_dump()
            if hasattr(job.error, "model_dump")
            else {"message": str(job.error)}
        )

    return IndexJobDetailResponse(
        id=str(job.id),
        repo_id=str(job.repo_id),
        state=job.state,
        kind=job.kind,
        shard_count=job.shard_count,
        shards_done=job.shards_done,
        head_commit_sha=job.head_commit_sha,
        base_commit_sha=job.base_commit_sha,
        current_phase=current_phase,
        current_file=current_file,
        counters=merged_counters,
        progress_pct=round(progress_pct, 1),
        is_terminal=is_terminal,
        eta_seconds=getattr(job, "eta_seconds", None),
        error=error_dict,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/{repo_id}/jobs/{job_id}/cancel")
async def cancel_index_job(
    repo_id: str, job_id: str, user=Depends(get_current_user)
):
    """Request cancellation of a running index job.

    Sets a Redis cancel flag so active shards stop processing.
    Also immediately transitions the job to ``cancelled`` in MongoDB so the
    idempotency guard doesn't treat it as still-running.
    """
    from datetime import UTC, datetime

    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)

    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job or str(job.repo_id) != repo_id:
        raise HTTPException(status_code=404, detail="Index job not found")

    if job.state not in TERMINAL_STATES:
        await index_progress.request_cancel(job_id)
        job.state = "cancelled"
        job.current_phase = "cancelled"
        job.finished_at = datetime.now(UTC)
        job.updated_at = datetime.now(UTC)
        await job.save()

    return {"job_id": job_id, "state": job.state, "cancel_requested": True}


@router.get("/{repo_id}/jobs/{job_id}/events")
async def stream_index_job_events(
    repo_id: str, job_id: str, _user=Depends(get_current_user)
):
    """SSE stream of indexing progress events.

    Emits ``event: progress`` every ~1 second and ``event: done`` when the
    job reaches a terminal state, then closes.
    """
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")

    job = await IndexJob.get(PydanticObjectId(job_id))
    if not job or str(job.repo_id) != repo_id:
        raise HTTPException(status_code=404, detail="Index job not found")

    async def _generate():
        while True:
            try:
                current_job = await IndexJob.get(PydanticObjectId(job_id))
                snap = await index_progress.snapshot(job_id)

                if current_job:
                    chunks_total = int(snap.get("chunks_total") or 0)
                    chunks_done = int(snap.get("chunks_done") or 0)
                    progress_pct = (chunks_done / chunks_total * 100.0) if chunks_total else 0.0
                    payload = {
                        "state": current_job.state,
                        "current_phase": snap.get("phase") or snap.get("current_phase") or current_job.current_phase,
                        "current_file": snap.get("current_file") or current_job.current_file,
                        "chunks_done": chunks_done,
                        "chunks_total": chunks_total,
                        "progress_pct": round(progress_pct, 1),
                    }

                    if current_job.state in TERMINAL_STATES:
                        yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                        yield f"event: done\ndata: {json.dumps({'state': current_job.state})}\n\n"
                        break
                    else:
                        yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                else:
                    yield f"event: done\ndata: {json.dumps({'state': 'unknown'})}\n\n"
                    break

                await asyncio.sleep(1.0)
            except Exception as exc:
                logger.warning("SSE stream error for job %s: %s", job_id, exc)
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
