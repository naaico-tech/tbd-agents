import logging
from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.models.knowledge_item import KnowledgeContentType, KnowledgeItem
from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.services import token_manager

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """Manages knowledge sources (Qdrant vector DB and MongoDB/GridFS items)."""

    async def test_connection(self, source: KnowledgeSource) -> dict:
        """Test connectivity for a knowledge source.

        For VECTOR_DB (Qdrant): connects and verifies the collection exists.
        For MONGO_DB: always succeeds (local storage).
        """
        if source.source_type == KnowledgeSourceType.MONGO_DB:
            source.status = KnowledgeSourceStatus.CONNECTED
            source.last_error = None
            source.updated_at = datetime.now(UTC)
            await source.save()
            return {"success": True}

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
        self, source: KnowledgeSource, query: str, limit: int = 10
    ) -> list[dict]:
        """Query a Qdrant vector DB source by text (scroll, not semantic search).

        Phase 1 uses scroll to retrieve documents. Semantic search with
        embeddings is deferred to Phase 2.
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
            results, _ = await client.scroll(
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
                for point in results
            ]
        finally:
            await client.close()

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
        from app.db import init_db  # noqa: F401
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.config import settings

        client = AsyncIOMotorClient(settings.mongo_uri)
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

    async def delete_item(self, item: KnowledgeItem) -> None:
        """Delete a knowledge item and its associated GridFS file (if any)."""
        if item.file_id:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient

                from app.config import settings

                client = AsyncIOMotorClient(settings.mongo_uri)
                db = client[settings.mongo_db_name]
                fs = AsyncIOMotorGridFSBucket(db)
                await fs.delete(ObjectId(item.file_id))
            except Exception as exc:
                logger.warning("Failed to delete GridFS file %s: %s", item.file_id, exc)
        await item.delete()

    async def get_file_content(self, item: KnowledgeItem) -> bytes:
        """Retrieve file bytes from GridFS."""
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.config import settings

        client = AsyncIOMotorClient(settings.mongo_uri)
        db = client[settings.mongo_db_name]
        fs = AsyncIOMotorGridFSBucket(db)

        stream = await fs.open_download_stream(ObjectId(item.file_id))
        return await stream.read()

    async def build_knowledge_context(
        self, sources: list[KnowledgeSource], tags: list[str]
    ) -> str:
        """Aggregate knowledge text from resolved sources for system prompt injection.

        Returns an XML-formatted string with knowledge content from all sources.
        """
        if not sources and not tags:
            return ""

        sections: list[str] = []

        # Gather text from MongoDB-backed items by tags
        if tags:
            items = await self.get_items_by_tags(tags, limit=50)
            for item in items:
                if item.content_type == KnowledgeContentType.TEXT and item.text_content:
                    sections.append(
                        f'<item name="{item.name}" tags="{",".join(item.tags)}">\n'
                        f"{item.text_content}\n"
                        f"</item>"
                    )

        # Gather text from vector DB sources
        for source in sources:
            if source.source_type == KnowledgeSourceType.VECTOR_DB:
                try:
                    results = await self.query_vector_db(source, query="", limit=20)
                    for r in results:
                        text = r.get("text", "")
                        if text:
                            sections.append(
                                f'<item source="{source.name}">\n{text}\n</item>'
                            )
                except Exception as exc:
                    logger.warning(
                        "Failed to query vector DB '%s': %s", source.name, exc
                    )

        if not sections:
            return ""

        return "<knowledge>\n" + "\n".join(sections) + "\n</knowledge>"


knowledge_manager = KnowledgeManager()
