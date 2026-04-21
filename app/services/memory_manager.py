import logging
from datetime import UTC, datetime
from xml.sax.saxutils import escape, quoteattr

from app.config import settings
from app.models.memory import Memory, MemoryScope
from app.services import memory_stm

logger = logging.getLogger(__name__)


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

        Writes to both MongoDB (LTM) and Redis (STM) and enforces the
        per-agent LTM cap configured via ``ltm_max_entries``.
        """
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
    ) -> str:
        """Build a <memories> XML context block for system prompt injection.

        Reads from Redis STM first for speed.  Falls back to MongoDB LTM
        if the STM cache is empty or unavailable.
        """
        await self.prune()

        effective_limit = min(limit, settings.prompt_context_max_items)
        effective_max_chars = max_chars or settings.prompt_memory_char_budget
        item_char_limit = settings.prompt_context_item_char_limit

        memories_dicts: list[dict] = []

        # ── Try Redis STM first ──────────────────────────────────────────
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
