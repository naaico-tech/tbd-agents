"""REST API for the CodeRepository library."""

from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.code_repository import (
    CodeRepository,
    CodeRepositoryStatus,
)
from app.schemas.code_repository import (
    CodeRepositoryCreate,
    CodeRepositoryIndexResponse,
    CodeRepositoryResponse,
    CodeRepositorySyncResponse,
    CodeRepositoryUpdate,
)
from app.schemas.export_import import (
    CodeRepositoryExportBundle,
    CodeRepositoryImportBundle,
    ExportedCodeRepository,
    ImportResult,
)
from app.services.code_repository_manager import code_repository_manager

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


# ── Lifecycle: sync / index / search ─────────────────────────────────────────


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


@router.post("/{repo_id}/index", response_model=CodeRepositoryIndexResponse)
async def index_code_repository(repo_id: str, user=Depends(get_current_user)):
    repo = await CodeRepository.get(PydanticObjectId(repo_id))
    if not repo:
        raise HTTPException(status_code=404, detail="Code repository not found")
    _require_owner(repo, user)
    if not repo.local_path:
        await code_repository_manager.sync(repo, force=True)
    if repo.status == CodeRepositoryStatus.ERROR:
        return CodeRepositoryIndexResponse(
            status=repo.status,
            indexed=False,
            file_count=repo.file_count,
            reason="sync_failed",
            last_error=repo.last_error,
        )
    result = await code_repository_manager.index(repo)
    return CodeRepositoryIndexResponse(
        status=repo.status,
        indexed=bool(result.get("indexed")),
        file_count=repo.file_count,
        gitnexus_job_id=result.get("gitnexus_job_id"),
        reason=result.get("reason"),
        last_error=repo.last_error,
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
