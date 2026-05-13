import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.knowledge_item import KnowledgeContentType, KnowledgeItem
from app.models.knowledge_source import KnowledgeSource, KnowledgeSourceType
from app.schemas.knowledge import (
    KnowledgeItemCreate,
    KnowledgeItemResponse,
    KnowledgeItemUpdate,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
)
from app.services.knowledge_manager import knowledge_manager

router = APIRouter(prefix="/api/knowledge-items", tags=["knowledge-items"])


def _to_response(item: KnowledgeItem) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        id=str(item.id),
        source_id=item.source_id,
        name=item.name,
        content_type=item.content_type,
        text_content=item.text_content,
        file_id=item.file_id,
        file_name=item.file_name,
        file_size=item.file_size,
        mime_type=item.mime_type,
        tags=item.tags,
        metadata=item.metadata,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("", response_model=KnowledgeItemResponse, status_code=201)
async def create_knowledge_item(body: KnowledgeItemCreate, _user=Depends(get_current_user)):
    """Create a text-based knowledge item."""
    source = await KnowledgeSource.get(parse_doc_id(body.source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if source.source_type != KnowledgeSourceType.MONGO_DB:
        raise HTTPException(status_code=400, detail="Items can only be added to mongo_db sources")
    if body.content_type != KnowledgeContentType.TEXT:
        raise HTTPException(status_code=400, detail="Use /upload for file and image content types")
    item = KnowledgeItem(
        source_id=body.source_id,
        name=body.name,
        content_type=body.content_type,
        text_content=body.text_content,
        tags=body.tags,
        metadata=body.metadata,
    )
    await item.insert()
    return _to_response(item)


@router.post("/upload", response_model=KnowledgeItemResponse, status_code=201)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    source_id: str = Form(...),
    tags: str = Form("[]"),
    metadata: str = Form("{}"),
    _user=Depends(get_current_user),
):
    """Upload a file or image as a knowledge item."""
    source = await KnowledgeSource.get(parse_doc_id(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if source.source_type != KnowledgeSourceType.MONGO_DB:
        raise HTTPException(status_code=400, detail="File uploads only supported for mongo_db sources")

    try:
        tag_list = json.loads(tags)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid tags: expected a JSON array of strings")
    if not isinstance(tag_list, list) or any(not isinstance(tag, str) for tag in tag_list):
        raise HTTPException(status_code=400, detail="Invalid tags: expected a JSON array of strings")
    try:
        meta_dict = json.loads(metadata)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="metadata must be a valid JSON object")
    if not isinstance(meta_dict, dict):
        raise HTTPException(status_code=400, detail="metadata must be a valid JSON object")

    file_content = await file.read()
    mime = file.content_type or "application/octet-stream"

    # Determine content type from MIME
    content_type = KnowledgeContentType.FILE
    if mime.startswith("image/"):
        content_type = KnowledgeContentType.IMAGE

    item = await knowledge_manager.upload_file(
        source_id=str(source.id),
        file_name=file.filename or "unnamed",
        file_content=file_content,
        content_type=content_type,
        mime_type=mime,
        tags=tag_list,
        metadata=meta_dict,
    )
    return _to_response(item)


@router.get("", response_model=list[KnowledgeItemResponse])
async def list_knowledge_items(
    source_id: str | None = None,
    tags: str | None = None,
    content_type: str | None = None,
    _user=Depends(get_current_user),
):
    query: dict = {}
    if source_id:
        query["source_id"] = source_id
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        query["tags"] = {"$in": tag_list}
    if content_type:
        query["content_type"] = content_type
    if query:
        items = await KnowledgeItem.find(query).to_list()
    else:
        items = await KnowledgeItem.find_all().to_list()
    return [_to_response(i) for i in items]


@router.get("/{item_id}", response_model=KnowledgeItemResponse)
async def get_knowledge_item(item_id: str, _user=Depends(get_current_user)):
    item = await KnowledgeItem.get(parse_doc_id(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return _to_response(item)


@router.get("/{item_id}/content")
async def download_knowledge_file(item_id: str, _user=Depends(get_current_user)):
    """Download the file content of a knowledge item."""
    item = await KnowledgeItem.get(parse_doc_id(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    if not item.file_id:
        raise HTTPException(status_code=400, detail="Item has no associated file")
    content = await knowledge_manager.get_file_content(item)
    # Sanitize filename to prevent header injection
    safe_name = (item.file_name or "download").replace('"', '').replace('\r', '').replace('\n', '').replace('\\', '')
    return Response(
        content=content,
        media_type=item.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )


@router.put("/{item_id}", response_model=KnowledgeItemResponse)
async def update_knowledge_item(
    item_id: str, body: KnowledgeItemUpdate, _user=Depends(get_current_user)
):
    item = await KnowledgeItem.get(parse_doc_id(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await item.set(update_data)
    return _to_response(item)


@router.delete("/{item_id}", status_code=204)
async def delete_knowledge_item(item_id: str, _user=Depends(get_current_user)):
    item = await KnowledgeItem.get(parse_doc_id(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await knowledge_manager.delete_item(item)


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(body: KnowledgeQueryRequest, _user=Depends(get_current_user)):
    """Query knowledge items by tags."""
    items = await knowledge_manager.get_items_by_tags(body.tags, body.limit)
    return KnowledgeQueryResponse(items=[_to_response(i) for i in items])
