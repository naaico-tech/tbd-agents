"""Routes for CodeGraph repository indexing and querying."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.codegraph_repo import CodeGraphRepo, CodeGraphRepoStatus
from app.services.codegraph_service import codegraph_service

router = APIRouter(prefix="/api/codegraph", tags=["codegraph"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class RepoIndexRequest(BaseModel):
    name: str
    repo_url: str
    agent_ids: list[str] = []
    async_index: bool = True


class RepoResponse(BaseModel):
    id: str
    name: str
    repo_url: str
    local_path: str
    status: str
    indexed_at: datetime | None
    error_message: str | None
    agent_ids: list[str]
    mcp_server_id: str | None
    celery_task_id: str | None
    created_at: datetime
    updated_at: datetime


class QueryRequest(BaseModel):
    command: str
    args: list[str] = []


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(repo: CodeGraphRepo) -> RepoResponse:
    return RepoResponse(
        id=str(repo.id),
        name=repo.name,
        repo_url=repo.repo_url,
        local_path=repo.local_path,
        status=repo.status,
        indexed_at=repo.indexed_at,
        error_message=repo.error_message,
        agent_ids=repo.agent_ids,
        mcp_server_id=repo.mcp_server_id,
        celery_task_id=repo.celery_task_id,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/repos", response_model=RepoResponse, status_code=202)
async def create_repo(body: RepoIndexRequest, _user=Depends(get_current_user)):
    """Register and kick off indexing for a new repository.

    When ``async_index=True`` (default) the indexing is handed off to a Celery
    worker and the endpoint returns immediately with ``202 Accepted``.
    When ``async_index=False`` the indexing runs synchronously inside the
    request — useful for development / testing only.
    """
    repo = CodeGraphRepo(
        name=body.name,
        repo_url=body.repo_url,
        agent_ids=body.agent_ids,
        status=CodeGraphRepoStatus.PENDING,
    )
    await repo.insert()

    if body.async_index:
        from app.tasks.codegraph_tasks import index_repo_task  # noqa: PLC0415

        task = index_repo_task.delay(str(repo.id), body.repo_url, body.name)
        repo.celery_task_id = task.id
        await repo.save()
    else:
        await codegraph_service.index_repository(
            repo_url=body.repo_url,
            name=body.name,
            repo_id=str(repo.id),
        )
        # Re-fetch so the response reflects any state changes made by the service.
        refreshed = await CodeGraphRepo.get(parse_doc_id(str(repo.id)))
        if refreshed is not None:
            repo = refreshed

    return _to_response(repo)


@router.get("/repos", response_model=list[RepoResponse])
async def list_repos(_user=Depends(get_current_user)):
    """Return all registered CodeGraph repositories."""
    repos = await codegraph_service.list_repositories()
    return [_to_response(r) for r in repos]


@router.get("/repos/{repo_id}", response_model=RepoResponse)
async def get_repo(repo_id: str, _user=Depends(get_current_user)):
    """Fetch a single CodeGraph repository by ID."""
    repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="CodeGraph repository not found")
    return _to_response(repo)


@router.post("/repos/{repo_id}/reindex", response_model=RepoResponse, status_code=202)
async def reindex_repo(repo_id: str, _user=Depends(get_current_user)):
    """Trigger a re-index of an existing repository via a Celery task."""
    repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="CodeGraph repository not found")

    from app.tasks.codegraph_tasks import index_repo_task  # noqa: PLC0415

    task = index_repo_task.delay(str(repo.id), repo.repo_url, repo.name)
    repo.celery_task_id = task.id
    repo.status = CodeGraphRepoStatus.PENDING
    await repo.save()

    return _to_response(repo)


@router.delete("/repos/{repo_id}", status_code=204)
async def delete_repo(
    repo_id: str,
    delete_local: bool = Query(False),
    _user=Depends(get_current_user),
):
    """Remove a repository record and optionally its on-disk clone."""
    try:
        await codegraph_service.remove_repository(repo_id, delete_local=delete_local)
    except ValueError:
        raise HTTPException(status_code=404, detail="CodeGraph repository not found")


@router.post("/repos/{repo_id}/query")
async def query_repo(
    repo_id: str,
    body: QueryRequest,
    _user=Depends(get_current_user),
) -> dict:
    """Run an ad-hoc ``codegraph`` CLI query against an indexed repository."""
    repo = await CodeGraphRepo.get(parse_doc_id(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="CodeGraph repository not found")
    if repo.status != CodeGraphRepoStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"Repository is not ready for queries (current status: {repo.status})",
        )
    try:
        return await codegraph_service.query_cli(body.command, body.args, str(repo.id))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
