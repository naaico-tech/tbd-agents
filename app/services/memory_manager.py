import logging
from datetime import UTC, datetime
from xml.sax.saxutils import escape, quoteattr

from app.models.memory import Memory, MemoryScope

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages agent memory storage, retrieval, and lifecycle."""

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
        """Store a memory, upserting by (agent_id, scope, key)."""
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
            return existing

        memory = Memory(
            agent_id=agent_id,
            scope=scope,
            key=key,
            value=value,
            embedding=embedding,
            metadata=metadata or {},
            ttl=ttl,
        )
        await memory.insert()
        return memory

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
    ) -> str:
        """Build a <memories> XML context block for system prompt injection.

        Fetches agent-scope and global-scope memories. If a workflow_id is
        provided, also fetches session-scope memories for that workflow.
        """
        # Prune expired entries first
        await self.prune()

        memories: list[Memory] = []

        # Agent-scope memories
        agent_mems = await Memory.find(
            {"agent_id": agent_id, "scope": MemoryScope.AGENT}
        ).sort("-updated_at").limit(limit).to_list()
        memories.extend(agent_mems)

        # Global-scope memories
        global_mems = await Memory.find(
            {"scope": MemoryScope.GLOBAL}
        ).sort("-updated_at").limit(limit).to_list()
        memories.extend(global_mems)

        # Session-scope memories (per-workflow)
        if workflow_id:
            session_mems = await Memory.find(
                {
                    "agent_id": agent_id,
                    "scope": MemoryScope.SESSION,
                    "metadata.workflow_id": workflow_id,
                }
            ).sort("-updated_at").limit(limit).to_list()
            memories.extend(session_mems)

        if not memories:
            return ""

        sections: list[str] = []
        for mem in memories:
            sections.append(
                f'<memory key={quoteattr(mem.key)} scope={quoteattr(mem.scope)}>\n'
                f"{escape(mem.value)}\n"
                f"</memory>"
            )

        return "<memories>\n" + "\n".join(sections) + "\n</memories>"


memory_manager = MemoryManager()
