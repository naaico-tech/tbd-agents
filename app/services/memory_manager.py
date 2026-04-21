import logging
from datetime import UTC, datetime
from xml.sax.saxutils import escape, quoteattr

from app.config import settings
from app.models.memory import Memory, MemoryScope
from app.services import memory_stm
from app.services.embeddings import embeddings_service

logger = logging.getLogger(__name__)

# Qdrant collection used for agent memory vectors
_MEMORY_COLLECTION = "agent_memories"


def _clip_text(text: str, max_chars: int) -> str:
    """Trim text to a soft character budget while preserving useful prefix context."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


class MemoryManager:
    """Manages agent memory storage, retrieval, and lifecycle.

    Two-tier architecture:
    - **STM (Short-Term Memory)**: Last N memories per agent cached in Redis
      for fast system-prompt injection.
    - **LTM (Long-Term Memory)**: Up to M memories per agent persisted in
      MongoDB for durable storage and search/query.
    """

    async def store(
        self,
        agent_id: str,
        scope: MemoryScope,
        key: str,
        value: str,
        embedding: list[float] | None = None,
        metadata: dict | None = None,
        ttl: datetime | None = None,
    ) -> Memory:
        """Store a memory, upserting by (agent_id, scope, key).

        Writes to both MongoDB (LTM) and Redis (STM), enforces the per-agent
        LTM cap, and upserts the embedding vector to Qdrant when embeddings
        are enabled.
        """
        # ── Generate embedding if not supplied ──────────────────────────
        if embedding is None and settings.embeddings_enabled:
            embed_text = f"{key}: {value}"
            embedding = await embeddings_service.embed_one(embed_text)

        existing = await Memory.find_one(
            {"agent_id": agent_id, "scope": scope, "key": key}
        )
        if existing:
            update_data: dict = {
                "value": value,
                "updated_at": datetime.now(UTC),
            }
            if embedding is not None:
                update_data["embedding"] = embedding
            if metadata is not None:
                update_data["metadata"] = metadata
            if ttl is not None:
                update_data["ttl"] = ttl
            await existing.set(update_data)
            mem = existing
        else:
            mem = Memory(
                agent_id=agent_id,
                scope=scope,
                key=key,
                value=value,
                embedding=embedding,
                metadata=metadata or {},
                ttl=ttl,
            )
            await mem.insert()

        # ── Enforce LTM cap ──────────────────────────────────────────────
        await self._enforce_ltm_cap(agent_id)

        # ── Upsert vector to Qdrant ──────────────────────────────────────
        if embedding:
            await self._upsert_qdrant(agent_id, mem, embedding)

        # ── Push to Redis STM ────────────────────────────────────────────
        try:
            await memory_stm.push_memory(agent_id, {
                "scope": mem.scope,
                "key": mem.key,
                "value": mem.value,
                "agent_id": agent_id,
                "updated_at": mem.updated_at.isoformat(),
            })
        except Exception as exc:
            logger.warning("STM push failed for agent %s: %s", agent_id, exc)

        return mem

    async def _upsert_qdrant(
        self, agent_id: str, mem: Memory, embedding: list[float]
    ) -> None:
        """Upsert a memory vector to the shared Qdrant collection.

        Creates the collection if it does not exist yet.  Failures are
        non-fatal — logged as warnings only.
        """
        qdrant_url = getattr(settings, "qdrant_url", None)
        if not qdrant_url:
            return
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import (
                Distance,
                PointStruct,
                VectorParams,
            )

            client = AsyncQdrantClient(url=qdrant_url)
            try:
                collections = await client.get_collections()
                existing_names = {c.name for c in collections.collections}
                if _MEMORY_COLLECTION not in existing_names:
                    await client.create_collection(
                        _MEMORY_COLLECTION,
                        vectors_config=VectorParams(
                            size=settings.embeddings_dim,
                            distance=Distance.COSINE,
                        ),
                    )
                point_id = abs(hash(f"{agent_id}:{mem.scope}:{mem.key}")) % (2**63)
                await client.upsert(
                    collection_name=_MEMORY_COLLECTION,
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload={
                                "agent_id": agent_id,
                                "scope": str(mem.scope),
                                "key": mem.key,
                                "value": mem.value,
                            },
                        )
                    ],
                )
            finally:
                await client.close()
        except Exception as exc:
            logger.warning("Qdrant upsert failed for memory '%s': %s", mem.key, exc)

    async def _enforce_ltm_cap(self, agent_id: str) -> None:
        """Remove oldest memories when the per-agent LTM cap is exceeded."""
        cap = settings.ltm_max_entries
        if cap <= 0:
            return  # unlimited

        total = await Memory.find({"agent_id": agent_id}).count()
        if total <= cap:
            return

        excess = total - cap
        oldest = (
            await Memory.find({"agent_id": agent_id})
            .sort("updated_at")
            .limit(excess)
            .to_list()
        )
        for mem in oldest:
            await mem.delete()

        logger.info(
            "LTM cap enforced for agent %s: removed %d oldest memories", agent_id, excess
        )

    async def retrieve(
        self, agent_id: str, scope: MemoryScope, key: str
    ) -> Memory | None:
        """Retrieve a single memory by exact (agent_id, scope, key) match."""
        return await Memory.find_one(
            {"agent_id": agent_id, "scope": scope, "key": key}
        )

    async def search(
        self,
        agent_id: str,
        query: str,
        scope: MemoryScope | None = None,
        limit: int = 10,
    ) -> list[Memory]:
        """Search memories by keyword match on key and value fields."""
        filter_query: dict = {"agent_id": agent_id}
        if scope:
            filter_query["scope"] = scope

        # Text-based keyword search across key and value
        filter_query["$or"] = [
            {"key": {"$regex": query, "$options": "i"}},
            {"value": {"$regex": query, "$options": "i"}},
        ]

        return await Memory.find(filter_query).sort("-updated_at").limit(limit).to_list()

    async def search_semantic(
        self,
        agent_id: str,
        query: str,
        scope: MemoryScope | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        """Semantic similarity search over Qdrant agent_memories collection.

        Returns a list of payload dicts sorted by relevance.  Falls back to
        an empty list when embeddings are unavailable or Qdrant is not
        configured.
        """
        qdrant_url = getattr(settings, "qdrant_url", None)
        if not qdrant_url or not settings.embeddings_enabled:
            return []

        query_vec = await embeddings_service.embed_one(query)
        if query_vec is None:
            return []

        k = top_k or settings.memory_retrieval_top_k

        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            client = AsyncQdrantClient(url=qdrant_url)
            try:
                query_filter = Filter(
                    must=[FieldCondition(key="agent_id", match=MatchValue(value=agent_id))]
                )
                if scope:
                    query_filter.must.append(  # type: ignore[union-attr]
                        FieldCondition(key="scope", match=MatchValue(value=str(scope)))
                    )
                results = await client.query_points(
                    collection_name=_MEMORY_COLLECTION,
                    query=query_vec,
                    query_filter=query_filter,
                    limit=k,
                    with_payload=True,
                )
                return [
                    point.payload
                    for point in results.points
                    if point.payload
                ]
            finally:
                await client.close()
        except Exception as exc:
            logger.warning("Qdrant semantic memory search failed: %s", exc)
            return []

    async def prune(self) -> int:
        """Remove expired memories (where ttl < now)."""
        now = datetime.now(UTC)
        result = await Memory.find(
            {"ttl": {"$ne": None, "$lt": now}}
        ).delete()
        count = result.deleted_count if result else 0
        if count:
            logger.info("Pruned %d expired memories", count)
        return count

    async def list_memories(
        self,
        agent_id: str,
        scope: MemoryScope | None = None,
        tags: list[str] | None = None,
    ) -> list[Memory]:
        """List memories with optional scope and tag filters."""
        filter_query: dict = {"agent_id": agent_id}
        if scope:
            filter_query["scope"] = scope
        if tags:
            filter_query["metadata.tags"] = {"$in": tags}

        return await Memory.find(filter_query).sort("-updated_at").to_list()

    async def build_memory_context(
        self,
        agent_id: str,
        workflow_id: str | None = None,
        limit: int = 50,
        max_chars: int | None = None,
        query: str | None = None,
    ) -> str:
        """Build a <memories> XML context block for system prompt injection.

        When *query* is provided and embeddings are available, performs
        semantic retrieval via Qdrant to surface the most relevant memories.
        Otherwise reads from Redis STM first for speed and falls back to
        MongoDB LTM.
        """
        await self.prune()

        effective_limit = min(limit, settings.prompt_context_max_items)
        effective_max_chars = max_chars or settings.prompt_memory_char_budget
        item_char_limit = settings.prompt_context_item_char_limit

        memories_dicts: list[dict] = []

        # ── Semantic retrieval (if query provided) ───────────────────────
        if query and settings.embeddings_enabled:
            semantic_hits = await self.search_semantic(
                agent_id, query, top_k=settings.memory_retrieval_top_k
            )
            if semantic_hits:
                memories_dicts = semantic_hits

        # ── Try Redis STM next ───────────────────────────────────────────
        if not memories_dicts:
            try:
                stm_entries = await memory_stm.get_recent_memories(agent_id, limit=effective_limit)
                if stm_entries:
                    memories_dicts = stm_entries
            except Exception as exc:
                logger.warning("STM read failed for agent %s, falling back to LTM: %s", agent_id, exc)

        # ── Fallback to MongoDB LTM ──────────────────────────────────────
        if not memories_dicts:
            memories: list[Memory] = []

            agent_mems = await Memory.find(
                {"agent_id": agent_id, "scope": MemoryScope.AGENT}
            ).sort("-updated_at").limit(effective_limit).to_list()
            memories.extend(agent_mems)

            global_mems = await Memory.find(
                {"scope": MemoryScope.GLOBAL}
            ).sort("-updated_at").limit(effective_limit).to_list()
            memories.extend(global_mems)

            if workflow_id:
                session_mems = await Memory.find(
                    {
                        "agent_id": agent_id,
                        "scope": MemoryScope.SESSION,
                        "metadata.workflow_id": workflow_id,
                    }
                ).sort("-updated_at").limit(effective_limit).to_list()
                memories.extend(session_mems)

            memories_dicts = [
                {"key": m.key, "scope": m.scope, "value": m.value}
                for m in memories
            ]

        if not memories_dicts:
            return ""

        seen: set[tuple[str, str]] = set()
        sections: list[str] = []
        total_chars = len("<memories>\n\n</memories>")
        for mem in memories_dicts:
            scope = str(mem.get("scope", ""))
            key = str(mem.get("key", ""))
            identity = (scope, key)
            if identity in seen:
                continue
            seen.add(identity)

            section_prefix = f'<memory key={quoteattr(key)} scope={quoteattr(scope)}>\n'
            section_suffix = "\n</memory>"
            remaining_budget = effective_max_chars - total_chars - (1 if sections else 0)
            value_budget = remaining_budget - len(section_prefix) - len(section_suffix)
            if value_budget <= 0:
                break
            value = _clip_text(
                str(mem.get("value", "")),
                min(item_char_limit, value_budget),
            )
            section = (
                section_prefix
                + f"{escape(value)}\n"
                + "</memory>"
            )
            if total_chars + len(section) + (1 if sections else 0) > effective_max_chars:
                break
            sections.append(section)
            total_chars += len(section) + 1
            if len(sections) >= effective_limit:
                break

        if not sections:
            return ""

        return "<memories>\n" + "\n".join(sections) + "\n</memories>"


memory_manager = MemoryManager()
