from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.memory import Memory, MemoryScope
from app.schemas.memory import (
    MemoryCreate,
    MemoryResponse,
    MemorySearchRequest,
    MemoryUpdate,
)
from app.services import memory_stm
from app.services.memory_manager import memory_manager

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _to_response(mem: Memory) -> MemoryResponse:
    return MemoryResponse(
        id=str(mem.id),
        agent_id=mem.agent_id,
        scope=mem.scope,
        key=mem.key,
        value=mem.value,
        embedding=mem.embedding,
        metadata=mem.metadata,
        ttl=mem.ttl,
        created_at=mem.created_at,
        updated_at=mem.updated_at,
    )


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(body: MemoryCreate, _user=Depends(get_current_user)):
    mem = await memory_manager.store(
        agent_id=body.agent_id,
        scope=body.scope,
        key=body.key,
        value=body.value,
        embedding=body.embedding,
        metadata=body.metadata,
        ttl=body.ttl,
    )
    return _to_response(mem)


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    agent_id: str | None = None,
    scope: MemoryScope | None = None,
    tags: str | None = None,
    _user=Depends(get_current_user),
):
    if not agent_id:
        # List all memories (admin use)
        query: dict = {}
        if scope:
            query["scope"] = scope
        if query:
            items = await Memory.find(query).to_list()
        else:
            items = await Memory.find_all().to_list()
        return [_to_response(m) for m in items]

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    items = await memory_manager.list_memories(agent_id, scope, tag_list)
    return [_to_response(m) for m in items]


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: str, _user=Depends(get_current_user)):
    mem = await Memory.get(parse_doc_id(memory_id))
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _to_response(mem)


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str, body: MemoryUpdate, _user=Depends(get_current_user)
):
    mem = await Memory.get(parse_doc_id(memory_id))
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await mem.set(update_data)
    return _to_response(mem)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, _user=Depends(get_current_user)):
    mem = await Memory.get(parse_doc_id(memory_id))
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    # Remove from Redis STM as well
    try:
        await memory_stm.remove_memory(mem.agent_id, mem.scope, mem.key)
    except Exception:
        pass  # STM removal is best-effort
    await mem.delete()


@router.post("/search", response_model=list[MemoryResponse])
async def search_memories(body: MemorySearchRequest, _user=Depends(get_current_user)):
    results = await memory_manager.search(
        agent_id=body.agent_id,
        query=body.query,
        scope=body.scope,
        limit=body.limit,
    )
    return [_to_response(m) for m in results]


@router.get("/stm/{agent_id}")
async def get_stm_memories(agent_id: str, _user=Depends(get_current_user)):
    """Return Short-Term Memory entries from Redis for the given agent."""
    try:
        entries = await memory_stm.get_recent_memories(agent_id)
    except Exception:
        entries = []
    return entries
