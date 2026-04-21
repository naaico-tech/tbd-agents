"""Tests for Knowledge Base models and schemas."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.knowledge_item import KnowledgeContentType, KnowledgeItem
from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.schemas.knowledge import (
    KnowledgeItemCreate,
    KnowledgeItemResponse,
    KnowledgeItemUpdate,
    KnowledgeQueryRequest,
    KnowledgeSourceCreate,
    KnowledgeSourceResponse,
    KnowledgeSourceUpdate,
)
from app.services.knowledge_manager import KnowledgeManager


# ── KnowledgeSource Model ───────────────────────────────────────────────────


class TestKnowledgeSourceModel:
    def test_source_defaults(self):
        s = KnowledgeSource.model_construct(
            name="test-source",
            source_type=KnowledgeSourceType.MONGO_DB,
        )
        assert s.name == "test-source"
        assert s.source_type == KnowledgeSourceType.MONGO_DB
        assert KnowledgeSource.model_fields["description"].default == ""
        assert KnowledgeSource.model_fields["status"].default == KnowledgeSourceStatus.REGISTERED

    def test_vector_db_source(self):
        s = KnowledgeSource.model_construct(
            name="qdrant-docs",
            source_type=KnowledgeSourceType.VECTOR_DB,
            connection_config={
                "url": "http://localhost:6333",
                "collection": "documents",
                "api_key_token_name": "qdrant-key",
            },
            tags=["docs", "internal"],
        )
        assert s.source_type == KnowledgeSourceType.VECTOR_DB
        assert s.connection_config["collection"] == "documents"
        assert s.tags == ["docs", "internal"]

    def test_mongo_db_source(self):
        s = KnowledgeSource.model_construct(
            name="local-docs",
            source_type=KnowledgeSourceType.MONGO_DB,
            tags=["faq"],
        )
        assert s.source_type == KnowledgeSourceType.MONGO_DB

    def test_source_type_enum_values(self):
        assert KnowledgeSourceType.VECTOR_DB == "vector_db"
        assert KnowledgeSourceType.MONGO_DB == "mongo_db"

    def test_status_enum_values(self):
        assert KnowledgeSourceStatus.REGISTERED == "registered"
        assert KnowledgeSourceStatus.CONNECTED == "connected"
        assert KnowledgeSourceStatus.ERROR == "error"

    def test_tags_default_empty(self):
        assert KnowledgeSource.model_fields["tags"].default_factory() == []

    def test_connection_config_default_empty(self):
        assert KnowledgeSource.model_fields["connection_config"].default_factory() == {}


# ── KnowledgeItem Model ─────────────────────────────────────────────────────


class TestKnowledgeItemModel:
    def test_text_item(self):
        i = KnowledgeItem.model_construct(
            source_id="src123",
            name="FAQ entry",
            content_type=KnowledgeContentType.TEXT,
            text_content="What is TBD Agents? A multi-agent API hub.",
            tags=["faq"],
        )
        assert i.content_type == KnowledgeContentType.TEXT
        assert i.text_content is not None
        assert i.file_id is None

    def test_file_item(self):
        i = KnowledgeItem.model_construct(
            source_id="src123",
            name="report.pdf",
            content_type=KnowledgeContentType.FILE,
            file_id="gridfs123",
            file_name="report.pdf",
            file_size=1024,
            mime_type="application/pdf",
            tags=["reports"],
        )
        assert i.content_type == KnowledgeContentType.FILE
        assert i.file_id == "gridfs123"
        assert i.file_size == 1024

    def test_image_item(self):
        i = KnowledgeItem.model_construct(
            source_id="src123",
            name="diagram.png",
            content_type=KnowledgeContentType.IMAGE,
            file_id="gridfs456",
            file_name="diagram.png",
            mime_type="image/png",
        )
        assert i.content_type == KnowledgeContentType.IMAGE

    def test_content_type_enum_values(self):
        assert KnowledgeContentType.TEXT == "text"
        assert KnowledgeContentType.FILE == "file"
        assert KnowledgeContentType.IMAGE == "image"

    def test_tags_default_empty(self):
        assert KnowledgeItem.model_fields["tags"].default_factory() == []

    def test_metadata_default_empty(self):
        assert KnowledgeItem.model_fields["metadata"].default_factory() == {}

    def test_item_with_metadata(self):
        i = KnowledgeItem.model_construct(
            source_id="src123",
            name="note",
            content_type=KnowledgeContentType.TEXT,
            text_content="Important info",
            metadata={"author": "admin", "version": 2},
        )
        assert i.metadata["author"] == "admin"
        assert i.metadata["version"] == 2


# ── KnowledgeSource Schemas ─────────────────────────────────────────────────


class TestKnowledgeSourceSchemas:
    def test_create_schema(self):
        data = KnowledgeSourceCreate(
            name="my-source",
            source_type="vector_db",
            connection_config={"url": "http://localhost:6333", "collection": "docs"},
            tags=["docs"],
        )
        assert data.name == "my-source"
        assert data.source_type == "vector_db"

    def test_create_defaults(self):
        data = KnowledgeSourceCreate(name="min", source_type="mongo_db")
        assert data.description == ""
        assert data.connection_config == {}
        assert data.tags == []

    def test_update_schema_all_optional(self):
        data = KnowledgeSourceUpdate()
        assert data.name is None
        assert data.tags is None

    def test_update_partial(self):
        data = KnowledgeSourceUpdate(tags=["new-tag"])
        dumped = data.model_dump(exclude_none=True)
        assert dumped == {"tags": ["new-tag"]}

    def test_response_schema(self):
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        resp = KnowledgeSourceResponse(
            id="abc123",
            name="src",
            description="",
            source_type="mongo_db",
            connection_config={},
            tags=[],
            status="registered",
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == "abc123"
        assert resp.status == "registered"


# ── KnowledgeItem Schemas ───────────────────────────────────────────────────


class TestKnowledgeItemSchemas:
    def test_create_schema(self):
        data = KnowledgeItemCreate(
            source_id="src123",
            name="entry",
            content_type="text",
            text_content="Hello",
            tags=["greeting"],
        )
        assert data.source_id == "src123"
        assert data.content_type == "text"

    def test_create_defaults(self):
        data = KnowledgeItemCreate(source_id="src", name="item")
        assert data.content_type == "text"
        assert data.tags == []
        assert data.metadata == {}

    def test_update_schema(self):
        data = KnowledgeItemUpdate(tags=["updated"])
        dumped = data.model_dump(exclude_none=True)
        assert dumped == {"tags": ["updated"]}

    def test_query_request(self):
        q = KnowledgeQueryRequest(tags=["faq", "docs"])
        assert q.limit == 10
        assert len(q.tags) == 2

    def test_query_request_custom_limit(self):
        q = KnowledgeQueryRequest(tags=["faq"], limit=5)
        assert q.limit == 5

    def test_response_schema(self):
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        resp = KnowledgeItemResponse(
            id="item123",
            source_id="src123",
            name="test",
            content_type="text",
            text_content="hello",
            file_id=None,
            file_name=None,
            file_size=None,
            mime_type=None,
            tags=["test"],
            metadata={},
            created_at=now,
            updated_at=now,
        )
        assert resp.id == "item123"
        assert resp.content_type == "text"


# ── Agent Knowledge Fields ───────────────────────────────────────────────────


class TestAgentKnowledgeFields:
    def test_agent_knowledge_defaults(self):
        from app.models.agent import Agent

        assert Agent.model_fields["knowledge_source_ids"].default_factory() == []
        assert Agent.model_fields["knowledge_tags"].default_factory() == []

    def test_agent_with_knowledge(self):
        from app.models.agent import Agent

        a = Agent.model_construct(
            name="smart-agent",
            knowledge_source_ids=["ks1", "ks2"],
            knowledge_tags=["docs", "faq"],
        )
        assert len(a.knowledge_source_ids) == 2
        assert a.knowledge_tags == ["docs", "faq"]


class TestKnowledgeManager:
    @pytest.fixture()
    def manager(self):
        return KnowledgeManager()

    @pytest.mark.asyncio
    async def test_build_knowledge_context_dedupes_and_respects_budget(self, manager):
        duplicate_text = "A" * 2000
        item = SimpleNamespace(
            content_type=KnowledgeContentType.TEXT,
            text_content=duplicate_text,
            name="doc-1",
            tags=["docs"],
        )
        source = SimpleNamespace(name="qdrant-1", source_type=KnowledgeSourceType.VECTOR_DB)

        with (
            patch.object(manager, "get_items_by_tags", new_callable=AsyncMock, return_value=[item, item]),
            patch.object(
                manager,
                "query_vector_db",
                new_callable=AsyncMock,
                return_value=[{"text": duplicate_text}, {"text": "B" * 100}],
            ),
        ):
            result = await manager.build_knowledge_context(
                [source],
                ["docs"],
                max_chars=350,
                item_limit=4,
            )

        assert result.startswith("<knowledge>")
        assert len(result) <= 350
        assert result.count("doc-1") == 1
        assert "..." in result

    @pytest.mark.asyncio
    async def test_build_knowledge_context_passes_query_to_vector_db(self, manager):
        """When query is provided, it should be forwarded to query_vector_db."""
        source = SimpleNamespace(name="qdrant-1", source_type=KnowledgeSourceType.VECTOR_DB)

        with (
            patch.object(manager, "get_items_by_tags", new_callable=AsyncMock, return_value=[]),
            patch.object(
                manager,
                "query_vector_db",
                new_callable=AsyncMock,
                return_value=[{"text": "semantic result"}],
            ) as mock_qvdb,
        ):
            result = await manager.build_knowledge_context(
                [source],
                [],
                query="what is the capital of France",
            )
        assert "semantic result" in result
        call_kwargs = mock_qvdb.call_args
        assert call_kwargs.kwargs.get("query") == "what is the capital of France" or \
               (len(call_kwargs.args) > 2 and call_kwargs.args[2] == "what is the capital of France")

    @pytest.mark.asyncio
    async def test_chunk_text_splits_correctly(self):
        from app.services.knowledge_manager import _chunk_text

        text = "a" * 3000
        chunks = _chunk_text(text, chunk_chars=1200, overlap_chars=150)
        assert len(chunks) > 1
        # Each chunk at most chunk_chars
        for c in chunks:
            assert len(c) <= 1200
        # Overlap: second chunk starts before first ends
        assert len(chunks[0]) == 1200
        assert len(chunks[1]) > 0

    def test_chunk_text_short_text_returns_one_chunk(self):
        from app.services.knowledge_manager import _chunk_text

        text = "short text"
        chunks = _chunk_text(text, chunk_chars=1200, overlap_chars=150)
        assert chunks == ["short text"]

    def test_chunk_text_exact_boundary(self):
        from app.services.knowledge_manager import _chunk_text

        text = "a" * 1200
        chunks = _chunk_text(text, chunk_chars=1200, overlap_chars=0)
        assert len(chunks) == 1
        assert chunks[0] == text

    @pytest.mark.asyncio
    async def test_store_text_item_creates_chunks(self, manager):
        """store_text_item should split text into chunks and insert each."""
        created_items = []

        async def fake_insert(self_item):
            created_items.append(self_item)

        text = "word " * 600  # 3000 chars → 2-3 chunks at 1200/150
        with (
            patch("app.services.knowledge_manager.settings") as mock_settings,
            patch("app.services.knowledge_manager.embeddings_service") as mock_emb,
            patch.object(KnowledgeItem, "insert", new=fake_insert),
        ):
            mock_settings.knowledge_chunk_chars = 1200
            mock_settings.knowledge_chunk_overlap_chars = 150
            mock_settings.embeddings_enabled = True
            mock_emb.embed_one = AsyncMock(return_value=[0.1, 0.2])

            items = await manager.store_text_item(
                source_id="src-1",
                name="long-doc",
                text=text,
                tags=["test"],
            )
        assert len(items) >= 2
        # Chunk indices should be contiguous
        indices = [item.metadata["chunk_index"] for item in items]
        assert indices == list(range(len(items)))
        # Each item should have the embedding stored in metadata
        for item in items:
            assert item.metadata.get("embedding") == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_query_vector_db_uses_scroll_when_no_query(self, manager):
        """When no query is provided, scroll fallback is used."""
        source = SimpleNamespace(
            name="src",
            connection_config={"url": "http://qdrant:6333", "collection": "test"},
        )
        mock_point = MagicMock()
        mock_point.id = 1
        mock_point.payload = {"text": "scroll result"}

        mock_client = AsyncMock()
        mock_client.scroll = AsyncMock(return_value=([mock_point], None))
        mock_client.close = AsyncMock()

        with patch("app.services.knowledge_manager.token_manager.get_token_value", new_callable=AsyncMock, return_value=None):
            with patch("app.services.knowledge_manager.AsyncQdrantClient", return_value=mock_client):
                results = await manager.query_vector_db(source, limit=5)
        assert results[0]["text"] == "scroll result"
        mock_client.scroll.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_vector_db_uses_query_points_when_query_provided(self, manager):
        """When query text + embeddings enabled, query_points should be called."""
        source = SimpleNamespace(
            name="src",
            connection_config={"url": "http://qdrant:6333", "collection": "test"},
        )
        mock_point = MagicMock()
        mock_point.id = 1
        mock_point.payload = {"text": "semantic result"}
        mock_point.score = 0.95

        mock_results = MagicMock()
        mock_results.points = [mock_point]

        mock_client = AsyncMock()
        mock_client.query_points = AsyncMock(return_value=mock_results)
        mock_client.close = AsyncMock()

        with (
            patch("app.services.knowledge_manager.settings") as mock_settings,
            patch("app.services.knowledge_manager.embeddings_service") as mock_emb,
            patch("app.services.knowledge_manager.token_manager.get_token_value", new_callable=AsyncMock, return_value=None),
            patch("app.services.knowledge_manager.AsyncQdrantClient", return_value=mock_client),
        ):
            mock_settings.embeddings_enabled = True
            mock_emb.embed_one = AsyncMock(return_value=[0.1, 0.2, 0.3])
            results = await manager.query_vector_db(source, limit=5, query="semantic search")
        assert results[0]["text"] == "semantic result"
        assert results[0]["score"] == 0.95
        mock_client.query_points.assert_awaited_once()
