from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.knowledge_retriever import _tokenise
from app.models.knowledge_base import KnowledgeBase, KnowledgeChunk
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    KnowledgeChunkCreate,
    KnowledgeChunkResponse,
    KnowledgeChunkUpdate,
)

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _kb_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=str(kb.id),
        name=kb.name,
        description=kb.description,
        tags=kb.tags,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _chunk_response(chunk: KnowledgeChunk) -> KnowledgeChunkResponse:
    return KnowledgeChunkResponse(
        id=str(chunk.id),
        knowledge_base_id=chunk.knowledge_base_id,
        content=chunk.content,
        source=chunk.source,
        created_at=chunk.created_at,
        updated_at=chunk.updated_at,
    )


# ── KnowledgeBase CRUD ────────────────────────────────────────────────────────


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(body: KnowledgeBaseCreate, _user=Depends(get_current_user)):
    kb = KnowledgeBase(**body.model_dump())
    await kb.insert()
    return _kb_response(kb)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(_user=Depends(get_current_user)):
    kbs = await KnowledgeBase.find_all().to_list()
    return [_kb_response(kb) for kb in kbs]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(kb_id: str, _user=Depends(get_current_user)):
    kb = await KnowledgeBase.get(PydanticObjectId(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return _kb_response(kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str, body: KnowledgeBaseUpdate, _user=Depends(get_current_user)
):
    kb = await KnowledgeBase.get(PydanticObjectId(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await kb.set(update_data)
    return _kb_response(kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(kb_id: str, _user=Depends(get_current_user)):
    kb = await KnowledgeBase.get(PydanticObjectId(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    # Cascade-delete all chunks
    await KnowledgeChunk.find(KnowledgeChunk.knowledge_base_id == kb_id).delete()
    await kb.delete()


# ── KnowledgeChunk CRUD ───────────────────────────────────────────────────────


@router.post("/{kb_id}/chunks", response_model=KnowledgeChunkResponse, status_code=201)
async def add_chunk(
    kb_id: str, body: KnowledgeChunkCreate, _user=Depends(get_current_user)
):
    kb = await KnowledgeBase.get(PydanticObjectId(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    chunk = KnowledgeChunk(
        knowledge_base_id=kb_id,
        content=body.content,
        tokens=_tokenise(body.content),
        source=body.source,
    )
    await chunk.insert()
    return _chunk_response(chunk)


@router.get("/{kb_id}/chunks", response_model=list[KnowledgeChunkResponse])
async def list_chunks(kb_id: str, _user=Depends(get_current_user)):
    kb = await KnowledgeBase.get(PydanticObjectId(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    chunks = await KnowledgeChunk.find(
        KnowledgeChunk.knowledge_base_id == kb_id
    ).to_list()
    return [_chunk_response(c) for c in chunks]


@router.get("/{kb_id}/chunks/{chunk_id}", response_model=KnowledgeChunkResponse)
async def get_chunk(kb_id: str, chunk_id: str, _user=Depends(get_current_user)):
    chunk = await KnowledgeChunk.get(PydanticObjectId(chunk_id))
    if not chunk or chunk.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return _chunk_response(chunk)


@router.put("/{kb_id}/chunks/{chunk_id}", response_model=KnowledgeChunkResponse)
async def update_chunk(
    kb_id: str,
    chunk_id: str,
    body: KnowledgeChunkUpdate,
    _user=Depends(get_current_user),
):
    chunk = await KnowledgeChunk.get(PydanticObjectId(chunk_id))
    if not chunk or chunk.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Chunk not found")
    update_data = body.model_dump(exclude_none=True)
    if "content" in update_data:
        update_data["tokens"] = _tokenise(update_data["content"])
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await chunk.set(update_data)
    return _chunk_response(chunk)


@router.delete("/{kb_id}/chunks/{chunk_id}", status_code=204)
async def delete_chunk(kb_id: str, chunk_id: str, _user=Depends(get_current_user)):
    chunk = await KnowledgeChunk.get(PydanticObjectId(chunk_id))
    if not chunk or chunk.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Chunk not found")
    await chunk.delete()
