import logging
import re
from datetime import UTC, datetime
from xml.sax.saxutils import escape, quoteattr

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.config import settings
from app.models.knowledge_item import KnowledgeContentType, KnowledgeItem
from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.observability import semantic_retrieval_hits_total, semantic_retrieval_results
from app.services import token_manager
from app.services.embeddings import embeddings_service

logger = logging.getLogger(__name__)


def _clip_text(text: str, max_chars: int) -> str:
    """Trim text to a soft character budget while preserving useful prefix context."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _chunk_text(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    """Split *text* into overlapping character-based chunks.

    Returns a list of non-empty chunks.  The last chunk may be shorter than
    *chunk_chars*.  When *text* fits in a single chunk it is returned as-is.
    """
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_chars - overlap_chars
    return [c for c in chunks if c.strip()]


class KnowledgeManager:
    """Manages knowledge sources (Qdrant vector DB, pgvector, and MongoDB/GridFS items)."""

    async def test_connection(self, source: KnowledgeSource) -> dict:
        """Test connectivity for a knowledge source.

        For VECTOR_DB (Qdrant): connects and verifies the collection exists.
        For PGVECTOR: connects via asyncpg and checks the pgvector extension.
        For MONGO_DB: always succeeds (local storage).
        """
        if source.source_type == KnowledgeSourceType.MONGO_DB:
            source.status = KnowledgeSourceStatus.CONNECTED
            source.last_error = None
            source.updated_at = datetime.now(UTC)
            await source.save()
            return {"success": True}

        if source.source_type == KnowledgeSourceType.PGVECTOR:
            try:
                import asyncpg

                collection = source.connection_config.get("collection", "")
                dsn_token_name = source.connection_config.get("dsn_token_name")

                if dsn_token_name:
                    dsn = await token_manager.get_token_value(dsn_token_name)
                else:
                    dsn = source.connection_config.get("dsn", "")

                if not dsn:
                    raise ValueError("No DSN configured for pgvector source")

                conn = await asyncpg.connect(dsn)
                try:
                    row = await conn.fetchrow(
                        "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                    )
                    if row is None:
                        raise RuntimeError(
                            "pgvector extension is not installed in the target database"
                        )
                    logger.info(
                        "pgvector extension confirmed; collection='%s'", collection
                    )
                finally:
                    await conn.close()

                source.status = KnowledgeSourceStatus.CONNECTED
                source.last_error = None
                source.updated_at = datetime.now(UTC)
                await source.save()
                return {
                    "success": True,
                    "status": "connected",
                    "extension": "vector",
                    "collection": collection,
                }
            except Exception as exc:
                source.status = KnowledgeSourceStatus.ERROR
                source.last_error = str(exc)[:500]
                source.updated_at = datetime.now(UTC)
                await source.save()
                return {"success": False, "error": str(exc)[:500]}

        # VECTOR_DB (Qdrant)
        try:
            from qdrant_client import AsyncQdrantClient

            url = source.connection_config.get("url", "")
            collection = source.connection_config.get("collection", "")
            api_key_token_name = source.connection_config.get("api_key_token_name")

            api_key = None
            if api_key_token_name:
                api_key = await token_manager.get_token_value(api_key_token_name)

            client = AsyncQdrantClient(url=url, api_key=api_key)
            try:
                info = await client.get_collection(collection)
                logger.info("Qdrant collection '%s': %d points", collection, info.points_count)
            finally:
                await client.close()

            source.status = KnowledgeSourceStatus.CONNECTED
            source.last_error = None
            source.updated_at = datetime.now(UTC)
            await source.save()
            return {"success": True}
        except Exception as exc:
            source.status = KnowledgeSourceStatus.ERROR
            source.last_error = str(exc)[:500]
            source.updated_at = datetime.now(UTC)
            await source.save()
            return {"success": False, "error": str(exc)[:500]}

    async def query_vector_db(
        self,
        source: KnowledgeSource,
        limit: int = 10,
        query: str | None = None,
    ) -> list[dict]:
        """Retrieve documents from a Qdrant vector DB source.

        When *query* is provided and embeddings are available, uses semantic
        similarity search via ``query_points``.  Otherwise falls back to
        ``scroll`` for recency-based retrieval.
        """
        from qdrant_client import AsyncQdrantClient

        url = source.connection_config.get("url", "")
        collection = source.connection_config.get("collection", "")
        api_key_token_name = source.connection_config.get("api_key_token_name")

        api_key = None
        if api_key_token_name:
            api_key = await token_manager.get_token_value(api_key_token_name)

        client = AsyncQdrantClient(url=url, api_key=api_key)
        try:
            # ── Semantic search ──────────────────────────────────────────
            if query and settings.embeddings_enabled:
                query_vec = await embeddings_service.embed_one(query)
                if query_vec is not None:
                    results = await client.query_points(
                        collection_name=collection,
                        query=query_vec,
                        limit=limit,
                        with_payload=True,
                    )
                    hits = [
                        {
                            "id": str(point.id),
                            "text": point.payload.get("text", "") if point.payload else "",
                            "metadata": point.payload or {},
                            "score": point.score,
                        }
                        for point in results.points
                    ]
                    semantic_retrieval_results.labels(type="knowledge").observe(len(hits))
                    if hits:
                        semantic_retrieval_hits_total.labels(type="knowledge").inc()
                    return hits

            # ── Scroll fallback ──────────────────────────────────────────
            scroll_results, _ = await client.scroll(
                collection_name=collection,
                limit=limit,
                with_payload=True,
            )
            return [
                {
                    "id": str(point.id),
                    "text": point.payload.get("text", "") if point.payload else "",
                    "metadata": point.payload or {},
                }
                for point in scroll_results
            ]
        finally:
            await client.close()

    async def query_pgvector(
        self,
        source: KnowledgeSource,
        limit: int = 10,
        query: str | None = None,
    ) -> list[dict]:
        """Retrieve documents from a pgvector source.

        When *query* is provided and embeddings are available, performs a
        cosine-similarity search using the ``<=>`` operator.  Otherwise falls
        back to a recency-ordered ``SELECT`` on the collection table.

        The table is expected to have at least the columns:
          - ``id``      — primary key
          - ``text``    — document text
          - ``embedding`` — ``vector`` column (present when semantic search is used)
          - ``metadata`` — ``jsonb`` column (optional)
        """
        import asyncpg

        collection = source.connection_config.get("collection", "")
        dsn_token_name = source.connection_config.get("dsn_token_name")

        if dsn_token_name:
            dsn = await token_manager.get_token_value(dsn_token_name)
        else:
            dsn = source.connection_config.get("dsn", "")

        if not dsn:
            raise ValueError("No DSN configured for pgvector source")
        if not collection:
            raise ValueError("No collection (table name suffix) configured for pgvector source")
        if not re.match(r"^[a-zA-Z0-9_]+$", collection):
            raise ValueError(f"Invalid collection name: {collection!r}")

        table = f"langchain_pg_embedding_{collection}"

        conn = await asyncpg.connect(dsn)
        try:
            # ── Semantic search ──────────────────────────────────────────
            if query and settings.embeddings_enabled:
                query_vec = await embeddings_service.embed_one(query)
                if query_vec is not None:
                    vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"
                    rows = await conn.fetch(
                        f"""
                        SELECT id::text, document AS text, cmetadata AS metadata,
                               1 - (embedding <=> $1::vector) AS score
                        FROM {table}
                        ORDER BY embedding <=> $1::vector
                        LIMIT $2
                        """,
                        vec_literal,
                        limit,
                    )
                    hits = [
                        {
                            "id": row["id"],
                            "text": row["text"] or "",
                            "metadata": dict(row["metadata"]) if row["metadata"] else {},
                            "score": float(row["score"]),
                        }
                        for row in rows
                    ]
                    semantic_retrieval_results.labels(type="knowledge").observe(len(hits))
                    if hits:
                        semantic_retrieval_hits_total.labels(type="knowledge").inc()
                    return hits

            # ── Recency fallback ─────────────────────────────────────────
            rows = await conn.fetch(
                f"""
                SELECT id::text, document AS text, cmetadata AS metadata
                FROM {table}
                ORDER BY id DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                {
                    "id": row["id"],
                    "text": row["text"] or "",
                    "metadata": dict(row["metadata"]) if row["metadata"] else {},
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def store_text_item(
        self,
        source_id: str,
        name: str,
        text: str,
        tags: list[str],
        metadata: dict | None = None,
    ) -> list[KnowledgeItem]:
        """Store a text knowledge item, chunking it and embedding each chunk.

        Each chunk is saved as a separate KnowledgeItem with the chunk index
        in its metadata.  Embeddings are stored in the item's ``metadata``
        field (as the full float list is too large for MongoDB indexing) and
        NOT pushed to Qdrant here — Qdrant is queried via the external vector
        DB source.  The embedding is stored on the item so callers that have
        a Qdrant client can upsert them separately if needed.
        """
        chunk_chars = settings.knowledge_chunk_chars
        overlap_chars = settings.knowledge_chunk_overlap_chars
        chunks = _chunk_text(text, chunk_chars, overlap_chars)

        items: list[KnowledgeItem] = []
        for idx, chunk in enumerate(chunks):
            embed = (
                await embeddings_service.embed_one(chunk)
                if settings.embeddings_enabled
                else None
            )
            item_meta = dict(metadata or {})
            item_meta["chunk_index"] = idx
            item_meta["chunk_total"] = len(chunks)
            if embed:
                item_meta["embedding"] = embed

            item = KnowledgeItem(
                source_id=source_id,
                name=f"{name}[{idx}]" if len(chunks) > 1 else name,
                content_type=KnowledgeContentType.TEXT,
                text_content=chunk,
                tags=tags,
                metadata=item_meta,
            )
            await item.insert()
            items.append(item)

        return items

    async def get_items_by_tags(
        self, tags: list[str], limit: int = 10
    ) -> list[KnowledgeItem]:
        """Retrieve knowledge items matching any of the given tags."""
        return await KnowledgeItem.find(
            {"tags": {"$in": tags}},
        ).limit(limit).to_list()

    async def upload_file(
        self,
        source_id: str,
        file_name: str,
        file_content: bytes,
        content_type: KnowledgeContentType,
        mime_type: str,
        tags: list[str],
        metadata: dict,
    ) -> KnowledgeItem:
        """Store a file in GridFS and create a KnowledgeItem record."""
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.config import settings

        client = AsyncIOMotorClient(settings.mongo_uri)
        try:
            db = client[settings.mongo_db_name]
            fs = AsyncIOMotorGridFSBucket(db)

            grid_in = fs.open_upload_stream(file_name, metadata={"mime_type": mime_type})
            await grid_in.write(file_content)
            await grid_in.close()

            item = KnowledgeItem(
                source_id=source_id,
                name=file_name,
                content_type=content_type,
                file_id=str(grid_in._id),
                file_name=file_name,
                file_size=len(file_content),
                mime_type=mime_type,
                tags=tags,
                metadata=metadata,
            )
            await item.insert()
            return item
        finally:
            client.close()

    async def delete_item(self, item: KnowledgeItem) -> None:
        """Delete a knowledge item and its associated GridFS file (if any)."""
        if item.file_id:
            from motor.motor_asyncio import AsyncIOMotorClient

            from app.config import settings

            client = AsyncIOMotorClient(settings.mongo_uri)
            try:
                db = client[settings.mongo_db_name]
                fs = AsyncIOMotorGridFSBucket(db)
                await fs.delete(ObjectId(item.file_id))
            except Exception as exc:
                logger.warning("Failed to delete GridFS file %s: %s", item.file_id, exc)
            finally:
                client.close()
        await item.delete()

    async def get_file_content(self, item: KnowledgeItem) -> bytes:
        """Retrieve file bytes from GridFS."""
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.config import settings

        client = AsyncIOMotorClient(settings.mongo_uri)
        try:
            db = client[settings.mongo_db_name]
            fs = AsyncIOMotorGridFSBucket(db)

            stream = await fs.open_download_stream(ObjectId(item.file_id))
            return await stream.read()
        finally:
            client.close()

    async def build_knowledge_context(
        self,
        sources: list[KnowledgeSource],
        tags: list[str],
        *,
        max_chars: int | None = None,
        item_limit: int | None = None,
        query: str | None = None,
    ) -> str:
        """Aggregate knowledge text from resolved sources for system prompt injection.

        When *query* is provided, vector DB sources use semantic search;
        otherwise scroll is used.  Returns an XML-formatted string.
        """
        if not sources and not tags:
            return ""

        effective_max_chars = max_chars or settings.prompt_knowledge_char_budget
        effective_item_limit = item_limit or settings.prompt_context_max_items
        item_char_limit = settings.prompt_context_item_char_limit

        sections: list[str] = []
        seen_payloads: set[str] = set()
        total_chars = len("<knowledge>\n\n</knowledge>")

        def _append_section(section: str, dedupe_key: str) -> bool:
            nonlocal total_chars
            if dedupe_key in seen_payloads:
                return False
            if total_chars + len(section) + (1 if sections else 0) > effective_max_chars:
                return False
            seen_payloads.add(dedupe_key)
            sections.append(section)
            total_chars += len(section) + 1
            return True

        # Gather text from MongoDB-backed items by tags
        if tags:
            items = await self.get_items_by_tags(tags, limit=effective_item_limit * 2)
            for item in items:
                if item.content_type == KnowledgeContentType.TEXT and item.text_content:
                    section_prefix = (
                        f'<item name={quoteattr(item.name)}'
                        f' tags={quoteattr(",".join(item.tags))}>\n'
                    )
                    remaining_budget = effective_max_chars - total_chars - (1 if sections else 0)
                    text_budget = remaining_budget - len(section_prefix) - len("\n</item>")
                    if text_budget <= 0:
                        break
                    clipped_text = _clip_text(
                        item.text_content,
                        min(item_char_limit, text_budget),
                    )
                    if _append_section(
                        section_prefix
                        + f"{escape(clipped_text)}\n"
                        + "</item>",
                        dedupe_key=f"tag:{item.name}:{clipped_text}",
                    ) and len(sections) >= effective_item_limit:
                        break

        # Gather text from vector DB sources
        for source in sources:
            if len(sections) >= effective_item_limit:
                break
            if source.source_type == KnowledgeSourceType.VECTOR_DB:
                try:
                    remaining = max(1, effective_item_limit - len(sections))
                    results = await self.query_vector_db(source, limit=remaining, query=query)
                    for r in results:
                        text = r.get("text", "")
                        if text:
                            section_prefix = f'<item source={quoteattr(source.name)}>\n'
                            remaining_budget = (
                                effective_max_chars - total_chars - (1 if sections else 0)
                            )
                            text_budget = (
                                remaining_budget - len(section_prefix) - len("\n</item>")
                            )
                            if text_budget <= 0:
                                break
                            clipped_text = _clip_text(
                                text,
                                min(item_char_limit, text_budget),
                            )
                            appended = _append_section(
                                f'{section_prefix}{escape(clipped_text)}\n</item>',
                                dedupe_key=f"vector:{source.name}:{clipped_text}",
                            )
                            if not appended or len(sections) >= effective_item_limit:
                                break
                except Exception as exc:
                    logger.warning(
                        "Failed to query vector DB '%s': %s", source.name, exc
                    )
            elif source.source_type == KnowledgeSourceType.PGVECTOR:
                try:
                    remaining = max(1, effective_item_limit - len(sections))
                    results = await self.query_pgvector(source, limit=remaining, query=query)
                    for r in results:
                        text = r.get("text", "")
                        if text:
                            section_prefix = f'<item source={quoteattr(source.name)}>\n'
                            remaining_budget = (
                                effective_max_chars - total_chars - (1 if sections else 0)
                            )
                            text_budget = (
                                remaining_budget - len(section_prefix) - len("\n</item>")
                            )
                            if text_budget <= 0:
                                break
                            clipped_text = _clip_text(
                                text,
                                min(item_char_limit, text_budget),
                            )
                            appended = _append_section(
                                f'{section_prefix}{escape(clipped_text)}\n</item>',
                                dedupe_key=f"pgvector:{source.name}:{clipped_text}",
                            )
                            if not appended or len(sections) >= effective_item_limit:
                                break
                except Exception as exc:
                    logger.warning(
                        "Failed to query pgvector source '%s': %s", source.name, exc
                    )

        if not sections:
            return ""

        return "<knowledge>\n" + "\n".join(sections) + "\n</knowledge>"


knowledge_manager = KnowledgeManager()
