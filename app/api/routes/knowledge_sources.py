from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.knowledge_item import KnowledgeItem
from app.models.knowledge_source import KnowledgeSource, KnowledgeSourceStatus, KnowledgeSourceType
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
    if body.source_type not in (KnowledgeSourceType.VECTOR_DB, KnowledgeSourceType.MONGO_DB):
        raise HTTPException(status_code=400, detail="source_type must be 'vector_db' or 'mongo_db'")
    source = KnowledgeSource(
        name=body.name,
        description=body.description,
        source_type=KnowledgeSourceType(body.source_type),
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


@router.get("/{source_id}", response_model=KnowledgeSourceResponse)
async def get_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(PydanticObjectId(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return _to_response(source)


@router.put("/{source_id}", response_model=KnowledgeSourceResponse)
async def update_knowledge_source(
    source_id: str, body: KnowledgeSourceUpdate, _user=Depends(get_current_user)
):
    source = await KnowledgeSource.get(PydanticObjectId(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    update_data = body.model_dump(exclude_none=True)
    if "source_type" in update_data:
        if update_data["source_type"] not in (KnowledgeSourceType.VECTOR_DB, KnowledgeSourceType.MONGO_DB):
            raise HTTPException(status_code=400, detail="source_type must be 'vector_db' or 'mongo_db'")
        update_data["source_type"] = KnowledgeSourceType(update_data["source_type"])
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        source.status = KnowledgeSourceStatus.REGISTERED
        update_data["status"] = KnowledgeSourceStatus.REGISTERED
        await source.set(update_data)
    return _to_response(source)


@router.delete("/{source_id}", status_code=204)
async def delete_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(PydanticObjectId(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    # Cascade delete: remove all items belonging to this source
    items = await KnowledgeItem.find(
        KnowledgeItem.source_id == str(source.id),
    ).to_list()
    for item in items:
        await knowledge_manager.delete_item(item)
    await source.delete()


@router.post("/{source_id}/test", response_model=KnowledgeSourceTestResponse)
async def test_knowledge_source(source_id: str, _user=Depends(get_current_user)):
    source = await KnowledgeSource.get(PydanticObjectId(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    result = await knowledge_manager.test_connection(source)
    return KnowledgeSourceTestResponse(**result)
