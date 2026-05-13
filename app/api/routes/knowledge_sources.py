from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.knowledge_item import KnowledgeItem
from app.models.knowledge_source import KnowledgeSource, KnowledgeSourceStatus, KnowledgeSourceType
from app.schemas.export_import import (
    ExportedKnowledgeSource,
    ImportResult,
    KnowledgeSourceExportBundle,
    KnowledgeSourceImportBundle,
)
from app.schemas.knowledge import (
    KnowledgeSourceCreate,
    KnowledgeSourceResponse,
    KnowledgeSourceTestResponse,
    KnowledgeSourceUpdate,
)
from app.services.knowledge_manager import knowledge_manager

router = APIRouter(prefix="/api/knowledge-sources", tags=["knowledge-sources"])


def _to_response(source: KnowledgeSource) -> KnowledgeSourceResponse:
    return KnowledgeSourceResponse(
        id=str(source.id),
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        connection_config=source.connection_config,
        tags=source.tags,
        status=source.status,
        last_error=source.last_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@router.post("", response_model=KnowledgeSourceResponse, status_code=201)
async def create_knowledge_source(body: KnowledgeSourceCreate, _user=Depends(get_current_user)):
    source = KnowledgeSource(
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        connection_config=body.connection_config,
        tags=body.tags,
    )
    await source.insert()
    return _to_response(source)


@router.get("", response_model=list[KnowledgeSourceResponse])
async def list_knowledge_sources(
    tags: str | None = None,
    _user=Depends(get_current_user),
):
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        sources = await KnowledgeSource.find({"tags": {"$in": tag_list}}).to_list()
    else:
        sources = await KnowledgeSource.find_all().to_list()
    return [_to_response(s) for s in sources]


def _to_exported_ks(source: KnowledgeSource) -> ExportedKnowledgeSource:
    return ExportedKnowledgeSource(
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        connection_config=source.connection_config,
        tags=source.tags,
    )


@router.get("/export", response_model=KnowledgeSourceExportBundle)
async def export_knowledge_sources(_user=Depends(get_current_user)):
    sources = await KnowledgeSource.find_all().to_list()
    return KnowledgeSourceExportBundle(items=[_to_exported_ks(s) for s in sources])


@router.get("/{source_id}/export", response_model=KnowledgeSourceExportBundle)
async def export_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(parse_doc_id(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return KnowledgeSourceExportBundle(items=[_to_exported_ks(source)])


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_knowledge_sources(
    body: KnowledgeSourceImportBundle, _user=Depends(get_current_user)
):
    result = ImportResult()
    for item in body.items:
        try:
            source = KnowledgeSource(
                name=item.name,
                description=item.description,
                source_type=KnowledgeSourceType(item.source_type),
                connection_config=item.connection_config,
                tags=item.tags,
            )
            await source.insert()
            result.ids.append(str(source.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


@router.get("/{source_id}", response_model=KnowledgeSourceResponse)
async def get_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(parse_doc_id(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return _to_response(source)


@router.put("/{source_id}", response_model=KnowledgeSourceResponse)
async def update_knowledge_source(
    source_id: str, body: KnowledgeSourceUpdate, _user=Depends(get_current_user)
):
    source = await KnowledgeSource.get(parse_doc_id(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    update_data = body.model_dump(exclude_none=True)
    if "source_type" in update_data:
        update_data["source_type"] = KnowledgeSourceType(update_data["source_type"])
    connection_fields_updated = any(
        field in update_data for field in ("source_type", "connection_config")
    )
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        if connection_fields_updated:
            source.status = KnowledgeSourceStatus.REGISTERED
            source.last_error = None
            update_data["status"] = KnowledgeSourceStatus.REGISTERED
            update_data["last_error"] = None
        await source.set(update_data)
    return _to_response(source)


@router.delete("/{source_id}", status_code=204)
async def delete_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(parse_doc_id(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    # Cascade delete: remove all items belonging to this source
    items = await KnowledgeItem.find(
        {"source_id": str(source.id)},
    ).to_list()
    for item in items:
        await knowledge_manager.delete_item(item)
    await source.delete()


@router.post("/{source_id}/test", response_model=KnowledgeSourceTestResponse)
async def test_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(parse_doc_id(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    result = await knowledge_manager.test_connection(source)
    return KnowledgeSourceTestResponse(**result)
