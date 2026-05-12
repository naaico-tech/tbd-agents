"""
Tests for the PgvectorAdapter and pgvector-specific service integration.
All asyncpg and pgvector I/O is mocked — no real database required.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.knowledge_source import KnowledgeSource, KnowledgeSourceType
from app.services.vector_store import AbstractVectorStore, SearchResult, VectorPoint
from app.services.vector_store.pgvector_adapter import PgvectorAdapter

# ── Async context manager helper ──────────────────────────────────────────────


class AsyncContextManagerMock:
    """Minimal async context manager that yields a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


# ── PgvectorAdapter unit tests ────────────────────────────────────────────────


class TestPgvectorAdapter:
    """Unit tests for PgvectorAdapter with all asyncpg I/O mocked."""

    @pytest.fixture()
    def mock_pool_and_conn(self):
        """Return a (pool, conn) tuple with all asyncpg methods mocked."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value=None)
        conn.executemany = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)

        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncContextManagerMock(conn))
        pool.close = AsyncMock()
        return pool, conn

    @pytest.fixture()
    def adapter(self, mock_pool_and_conn):
        """Return a PgvectorAdapter with pool pre-injected (bypasses asyncpg.create_pool)."""
        pool, _ = mock_pool_and_conn
        a = PgvectorAdapter(dsn="postgresql://user:pass@localhost:5432/testdb", table_prefix="vs")
        a._pool = pool  # bypass _ensure_pool network call
        return a

    # ── create_collection ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_collection_executes_ddl(self, adapter, mock_pool_and_conn):
        """create_collection must issue CREATE TABLE and CREATE INDEX SQL."""
        _, conn = mock_pool_and_conn
        await adapter.create_collection("docs", 384)

        assert conn.execute.await_count >= 2
        executed_sqls = [str(c.args[0]) for c in conn.execute.await_args_list]
        assert any("CREATE TABLE" in sql for sql in executed_sqls)
        assert any("CREATE INDEX" in sql for sql in executed_sqls)

    @pytest.mark.asyncio
    async def test_create_collection_stores_metadata(self, adapter, mock_pool_and_conn):
        """create_collection populates the in-memory _meta_cache."""
        await adapter.create_collection("docs", 384, distance="cosine")
        assert "docs" in adapter._meta_cache
        assert adapter._meta_cache["docs"]["vector_size"] == 384
        assert adapter._meta_cache["docs"]["distance"] == "cosine"

    @pytest.mark.asyncio
    async def test_create_collection_uses_correct_ops_class_for_cosine(
        self, adapter, mock_pool_and_conn
    ):
        """Cosine distance uses vector_cosine_ops in the index DDL."""
        _, conn = mock_pool_and_conn
        await adapter.create_collection("docs", 384, distance="cosine")
        executed_sqls = [str(c.args[0]) for c in conn.execute.await_args_list]
        assert any("vector_cosine_ops" in sql for sql in executed_sqls)

    # ── collection_exists ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_collection_exists_true(self, adapter, mock_pool_and_conn):
        """collection_exists returns True when fetchrow returns a row."""
        _, conn = mock_pool_and_conn
        conn.fetchrow = AsyncMock(return_value={"1": 1})
        result = await adapter.collection_exists("docs")
        assert result is True

    @pytest.mark.asyncio
    async def test_collection_exists_false(self, adapter, mock_pool_and_conn):
        """collection_exists returns False when fetchrow returns None."""
        _, conn = mock_pool_and_conn
        conn.fetchrow = AsyncMock(return_value=None)
        result = await adapter.collection_exists("docs")
        assert result is False

    # ── upsert ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_calls_executemany(self, adapter, mock_pool_and_conn):
        """upsert calls conn.executemany with INSERT SQL and serialised params."""
        _, conn = mock_pool_and_conn
        points = [VectorPoint("id1", [0.1] * 384, {"k": "v"})]
        await adapter.upsert("docs", points)

        conn.executemany.assert_awaited_once()
        sql_arg, params_arg = conn.executemany.await_args.args
        assert "INSERT" in sql_arg
        assert "ON CONFLICT" in sql_arg
        # Params should be a list of tuples/lists: [(id, vector, payload_json)]
        assert len(params_arg) == 1
        assert params_arg[0][0] == "id1"
        assert params_arg[0][2] == json.dumps({"k": "v"})

    @pytest.mark.asyncio
    async def test_upsert_multiple_points(self, adapter, mock_pool_and_conn):
        """upsert passes all provided points to executemany."""
        _, conn = mock_pool_and_conn
        points = [
            VectorPoint(f"id{i}", [float(i)] * 8, {"index": i})
            for i in range(5)
        ]
        await adapter.upsert("docs", points)
        _, params_arg = conn.executemany.await_args.args
        assert len(params_arg) == 5

    # ── search ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_returns_results(self, adapter, mock_pool_and_conn):
        """search converts db rows into SearchResult instances with correct fields."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(
            return_value=[{"id": "id1", "score": 0.95, "payload": {"k": "v"}}]
        )
        adapter._meta_cache["docs"] = {"vector_size": 384, "distance": "cosine"}

        results = await adapter.search("docs", [0.1] * 384, limit=5)

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].id == "id1"
        assert results[0].score == pytest.approx(0.95)
        assert results[0].payload == {"k": "v"}

    @pytest.mark.asyncio
    async def test_search_returns_empty_list_on_missing_table(
        self, adapter, mock_pool_and_conn
    ):
        """search returns [] (no exception) when the table does not exist."""
        import asyncpg

        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(side_effect=asyncpg.UndefinedTableError("no table"))
        adapter._meta_cache["docs"] = {"distance": "cosine"}

        results = await adapter.search("docs", [0.1] * 384)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_filters(self, adapter, mock_pool_and_conn):
        """search with filters appends WHERE clause to the SQL."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(return_value=[])
        adapter._meta_cache["docs"] = {"vector_size": 384, "distance": "cosine"}

        await adapter.search("docs", [0.1] * 384, filters={"agent_id": "a1"})

        sql_arg = conn.fetch.await_args.args[0]
        assert "WHERE" in sql_arg
        assert "agent_id" in sql_arg

    # ── scroll ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_scroll_returns_results(self, adapter, mock_pool_and_conn):
        """scroll returns SearchResult instances ordered by created_at DESC."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "r1", "score": 0.0, "payload": {"key": "pref"}},
                {"id": "r2", "score": 0.0, "payload": {"key": "color"}},
            ]
        )

        results = await adapter.scroll("docs", limit=2)

        assert len(results) == 2
        assert all(r.score == 0.0 for r in results)
        assert results[0].id == "r1"
        assert results[1].id == "r2"

    @pytest.mark.asyncio
    async def test_scroll_sql_uses_created_at_order(self, adapter, mock_pool_and_conn):
        """scroll SQL orders by created_at DESC."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(return_value=[])

        await adapter.scroll("docs", limit=5, offset=0)

        sql_arg = conn.fetch.await_args.args[0]
        assert "created_at" in sql_arg.lower()
        assert "DESC" in sql_arg

    @pytest.mark.asyncio
    async def test_scroll_returns_empty_on_missing_table(self, adapter, mock_pool_and_conn):
        """scroll returns [] when the underlying table is missing."""
        import asyncpg

        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(side_effect=asyncpg.UndefinedTableError("no table"))

        results = await adapter.scroll("docs")
        assert results == []

    # ── delete ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_calls_execute(self, adapter, mock_pool_and_conn):
        """delete calls conn.execute with a DELETE SQL containing ANY($1)."""
        _, conn = mock_pool_and_conn
        await adapter.delete("docs", ["id1", "id2"])

        conn.execute.assert_awaited_once()
        sql_arg = conn.execute.await_args.args[0]
        assert "DELETE" in sql_arg
        assert "ANY" in sql_arg

    @pytest.mark.asyncio
    async def test_delete_passes_id_list(self, adapter, mock_pool_and_conn):
        """delete passes the list of IDs as a parameter."""
        _, conn = mock_pool_and_conn
        await adapter.delete("docs", ["id1", "id2"])

        _, positional = conn.execute.await_args.args[0], conn.execute.await_args.args[1:]
        assert ["id1", "id2"] in positional

    # ── count ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_count_returns_integer(self, adapter, mock_pool_and_conn):
        """count returns the integer count reported by the database."""
        _, conn = mock_pool_and_conn
        conn.fetchrow = AsyncMock(return_value={"cnt": 42})

        result = await adapter.count("docs")
        assert result == 42
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_count_queries_correct_table(self, adapter, mock_pool_and_conn):
        """count queries the sanitised table name for the given collection."""
        _, conn = mock_pool_and_conn
        conn.fetchrow = AsyncMock(return_value={"cnt": 0})

        await adapter.count("my-collection")

        sql_arg = conn.fetchrow.await_args.args[0]
        # Collection "my-collection" should be sanitised to "my_collection"
        assert "vs_my_collection" in sql_arg

    # ── close ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_close_closes_pool(self, adapter, mock_pool_and_conn):
        """close() calls pool.close() to release connections."""
        pool, _ = mock_pool_and_conn
        await adapter.close()
        pool.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_sets_pool_to_none(self, adapter, mock_pool_and_conn):
        """After close(), _pool is set to None."""
        await adapter.close()
        assert adapter._pool is None

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, adapter, mock_pool_and_conn):
        """Calling close() twice does not raise an error."""
        pool, _ = mock_pool_and_conn
        await adapter.close()
        await adapter.close()  # second call — _pool is None, should be a no-op
        pool.close.assert_awaited_once()  # only once

    # ── _table_name / name sanitisation ──────────────────────────────────────

    def test_table_name_sanitizes_collection(self):
        """Hyphens and slashes in collection names are replaced with underscores."""
        a = PgvectorAdapter(dsn="postgresql://localhost/test", table_prefix="vs")
        table = a._table_name("my-collection/1")
        # Should not contain hyphens or slashes
        assert "-" not in table
        assert "/" not in table
        assert table == "vs_my_collection_1"

    def test_table_name_prefix_is_sanitised(self):
        """Table prefix is sanitised at construction time."""
        a = PgvectorAdapter(dsn="postgresql://localhost/test", table_prefix="my-prefix")
        assert "-" not in a._table_prefix
        assert a._table_prefix == "my_prefix"

    def test_table_name_lowercases_collection(self):
        """Collection names are lowercased in the table name."""
        a = PgvectorAdapter(dsn="postgresql://localhost/test", table_prefix="vs")
        table = a._table_name("AgentMemories")
        assert table == "vs_agentmemories"

    # ── distance operator selection ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_distance_cosine_uses_correct_operator(
        self, adapter, mock_pool_and_conn
    ):
        """Cosine distance metric uses the <=> operator in the search SQL."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(return_value=[])
        adapter._meta_cache["docs"] = {"vector_size": 384, "distance": "cosine"}

        await adapter.search("docs", [0.1] * 384)

        sql_arg = conn.fetch.await_args.args[0]
        assert "<=>" in sql_arg

    @pytest.mark.asyncio
    async def test_distance_l2_uses_correct_operator(
        self, adapter, mock_pool_and_conn
    ):
        """L2 / euclid distance metric uses the <-> operator in the search SQL."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(return_value=[])
        adapter._meta_cache["docs"] = {"vector_size": 384, "distance": "l2"}

        await adapter.search("docs", [0.1] * 384)

        sql_arg = conn.fetch.await_args.args[0]
        assert "<->" in sql_arg

    @pytest.mark.asyncio
    async def test_distance_euclid_alias_uses_l2_operator(
        self, adapter, mock_pool_and_conn
    ):
        """'euclid' is an alias for 'l2' and must also produce the <-> operator."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(return_value=[])
        adapter._meta_cache["docs"] = {"vector_size": 384, "distance": "euclid"}

        await adapter.search("docs", [0.1] * 384)

        sql_arg = conn.fetch.await_args.args[0]
        assert "<->" in sql_arg

    @pytest.mark.asyncio
    async def test_distance_dot_uses_correct_operator(
        self, adapter, mock_pool_and_conn
    ):
        """Dot / inner_product distance uses the <#> operator."""
        _, conn = mock_pool_and_conn
        conn.fetch = AsyncMock(return_value=[])
        adapter._meta_cache["docs"] = {"vector_size": 384, "distance": "dot"}

        await adapter.search("docs", [0.1] * 384)

        sql_arg = conn.fetch.await_args.args[0]
        assert "<#>" in sql_arg


# ── MemoryManager integration with vector store ───────────────────────────────


class TestMemoryManagerWithVectorStore:
    """Integration tests for MemoryManager._upsert_vector_store and search_semantic."""

    @pytest.fixture()
    def manager(self):
        from app.services.memory_manager import MemoryManager

        return MemoryManager()

    @pytest.fixture()
    def mock_store(self):
        """A fully-mocked AbstractVectorStore for injection via get_vector_store."""
        store = AsyncMock(spec=AbstractVectorStore)
        store.create_collection = AsyncMock()
        store.upsert = AsyncMock()
        store.search = AsyncMock(return_value=[])
        return store

    @pytest.fixture()
    def sample_memory(self):
        """A mock Memory object with an embedding."""
        mem = MagicMock()
        mem.agent_id = "agent-1"
        mem.scope = "agent"
        mem.key = "test-key"
        mem.value = "test-value"
        mem.embedding = [0.1] * 384
        return mem

    # ── _upsert_vector_store ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_vector_store_creates_collection(
        self, manager, mock_store, sample_memory
    ):
        """create_collection is always called because it is idempotent (IF NOT EXISTS)."""
        with patch("app.services.memory_manager.get_vector_store", return_value=mock_store):
            await manager._upsert_vector_store(sample_memory)

        mock_store.create_collection.assert_awaited_once()
        mock_store.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_vector_store_always_calls_create_collection(
        self, manager, mock_store, sample_memory
    ):
        """create_collection is called unconditionally — it uses IF NOT EXISTS internally."""
        with patch("app.services.memory_manager.get_vector_store", return_value=mock_store):
            await manager._upsert_vector_store(sample_memory)

        mock_store.create_collection.assert_awaited_once()
        mock_store.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_vector_store_skips_when_no_embedding(
        self, manager, mock_store
    ):
        """When the memory has no embedding, upsert is NOT called."""
        mem = MagicMock()
        mem.embedding = None
        with patch("app.services.memory_manager.get_vector_store", return_value=mock_store):
            await manager._upsert_vector_store(mem)

        mock_store.upsert.assert_not_awaited()
        mock_store.create_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upsert_vector_store_skips_when_no_store(
        self, manager, sample_memory
    ):
        """When get_vector_store() returns None, no error is raised."""
        with patch("app.services.memory_manager.get_vector_store", return_value=None):
            # Should complete silently
            await manager._upsert_vector_store(sample_memory)

    @pytest.mark.asyncio
    async def test_upsert_vector_store_uses_correct_point_id(
        self, manager, mock_store, sample_memory
    ):
        """The VectorPoint id is composed of agent_id:scope:key."""
        with patch("app.services.memory_manager.get_vector_store", return_value=mock_store):
            await manager._upsert_vector_store(sample_memory)

        call_args = mock_store.upsert.await_args
        collection, points = call_args.args
        assert collection == "agent_memories"
        assert len(points) == 1
        expected_id = f"{sample_memory.agent_id}:{sample_memory.scope}:{sample_memory.key}"
        assert points[0].id == expected_id

    @pytest.mark.asyncio
    async def test_upsert_vector_store_error_is_non_fatal(
        self, manager, mock_store, sample_memory
    ):
        """Exceptions in _upsert_vector_store are caught and do not propagate."""
        mock_store.create_collection = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("app.services.memory_manager.get_vector_store", return_value=mock_store):
            # Should not raise
            await manager._upsert_vector_store(sample_memory)

    # ── search_semantic ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_semantic_returns_results(self, manager, mock_store):
        """search_semantic converts SearchResult objects into payload dicts."""
        mock_store.search = AsyncMock(
            return_value=[
                SearchResult("k1", 0.9, {"key": "k1", "value": "v1", "scope": "agent"}),
                SearchResult("k2", 0.7, {"key": "k2", "value": "v2", "scope": "agent"}),
            ]
        )
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
            patch("app.services.memory_manager.get_vector_store", return_value=mock_store),
        ):
            mock_settings.embeddings_enabled = True
            mock_settings.memory_retrieval_top_k = 8
            mock_emb.embed_one = AsyncMock(return_value=[0.1] * 384)

            results = await manager.search_semantic("agent-1", "test query")

        assert len(results) == 2
        assert results[0]["key"] == "k1"
        assert results[0]["value"] == "v1"
        assert results[0]["score"] == pytest.approx(0.9)
        assert results[1]["key"] == "k2"

    @pytest.mark.asyncio
    async def test_search_semantic_skips_when_no_store(self, manager):
        """search_semantic returns empty list when no vector store is configured."""
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
            patch("app.services.memory_manager.get_vector_store", return_value=None),
        ):
            mock_settings.embeddings_enabled = True
            mock_settings.memory_retrieval_top_k = 8
            mock_emb.embed_one = AsyncMock(return_value=[0.1] * 384)

            results = await manager.search_semantic("agent-1", "query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_semantic_returns_empty_when_embeddings_disabled(self, manager):
        """search_semantic short-circuits and returns [] when embeddings are off."""
        with patch("app.services.memory_manager.settings") as mock_settings:
            mock_settings.embeddings_enabled = False
            results = await manager.search_semantic("agent-1", "any query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_semantic_returns_empty_when_embedding_fails(self, manager):
        """search_semantic returns [] when embed_one returns None."""
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
        ):
            mock_settings.embeddings_enabled = True
            mock_emb.embed_one = AsyncMock(return_value=None)

            results = await manager.search_semantic("agent-1", "query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_semantic_passes_agent_filter(self, manager, mock_store):
        """search_semantic filters by agent_id in the vector store query."""
        mock_store.search = AsyncMock(return_value=[])
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
            patch("app.services.memory_manager.get_vector_store", return_value=mock_store),
        ):
            mock_settings.embeddings_enabled = True
            mock_settings.memory_retrieval_top_k = 5
            mock_emb.embed_one = AsyncMock(return_value=[0.1] * 384)

            await manager.search_semantic("agent-42", "test", top_k=5)

        search_kwargs = mock_store.search.await_args.kwargs
        assert search_kwargs.get("filters", {}).get("agent_id") == "agent-42"

    @pytest.mark.asyncio
    async def test_search_semantic_scope_filter(self, manager, mock_store):
        """search_semantic includes scope in the filter when provided."""
        from app.models.memory import MemoryScope

        mock_store.search = AsyncMock(return_value=[])
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
            patch("app.services.memory_manager.get_vector_store", return_value=mock_store),
        ):
            mock_settings.embeddings_enabled = True
            mock_settings.memory_retrieval_top_k = 5
            mock_emb.embed_one = AsyncMock(return_value=[0.1] * 384)

            await manager.search_semantic("agent-1", "test", scope=MemoryScope.AGENT)

        search_kwargs = mock_store.search.await_args.kwargs
        assert "scope" in search_kwargs.get("filters", {})


# ── KnowledgeManager pgvector tests ──────────────────────────────────────────


class TestKnowledgeManagerPgvector:
    """Tests for KnowledgeManager.test_connection and query_pgvector with pgvector sources."""

    @pytest.fixture()
    def manager(self):
        from app.services.knowledge_manager import KnowledgeManager

        return KnowledgeManager()

    @pytest.fixture()
    def pgvector_source(self):
        """A mock KnowledgeSource configured for pgvector."""
        source = MagicMock()
        source.source_type = KnowledgeSourceType.PGVECTOR
        source.connection_config = {
            "dsn": "postgresql://user:pass@localhost:5432/testdb",
            "collection": "documents",
        }
        source.save = AsyncMock()
        return source

    # ── test_connection ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_connection_success(self, manager, pgvector_source):
        """A healthy pgvector source with the extension installed → status=connected."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"1": 1})  # extension row found
        mock_conn.close = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            result = await manager.test_connection(pgvector_source)

        assert result["success"] is True
        assert result["status"] == "connected"
        assert result["extension"] == "vector"
        pgvector_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connection_missing_extension(self, manager, pgvector_source):
        """When the vector extension is absent, returns error with descriptive message."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)  # extension NOT found
        mock_conn.close = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            result = await manager.test_connection(pgvector_source)

        assert result["success"] is False
        assert "vector" in result["error"].lower() or "pgvector" in result["error"].lower()
        pgvector_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connection_failure(self, manager, pgvector_source):
        """When asyncpg.connect raises, returns error status."""
        with patch(
            "asyncpg.connect",
            new_callable=AsyncMock,
            side_effect=OSError("Connection refused"),
        ):
            result = await manager.test_connection(pgvector_source)

        assert result["success"] is False
        assert "Connection refused" in result["error"]
        pgvector_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connection_uses_dsn_token_when_configured(
        self, manager, pgvector_source
    ):
        """When dsn_token_name is set, it resolves the DSN via token_manager."""
        pgvector_source.connection_config = {
            "dsn_token_name": "my-db-secret",
            "collection": "docs",
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"1": 1})
        mock_conn.close = AsyncMock()

        with (
            patch(
                "app.services.knowledge_manager.token_manager.get_token_value",
                new_callable=AsyncMock,
                return_value="postgresql://resolved@localhost/db",
            ),
            patch(
                "asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn
            ) as mock_connect,
        ):
            result = await manager.test_connection(pgvector_source)

        assert result["success"] is True
        mock_connect.assert_awaited_once_with("postgresql://resolved@localhost/db")

    # ── query_pgvector ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_query_pgvector_semantic(self, manager, pgvector_source):
        """With embeddings enabled, query_pgvector uses <=> and returns scored results."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": "doc-1",
                    "text": "relevant document",
                    "metadata": {"source": "wiki"},
                    "score": 0.92,
                }
            ]
        )
        mock_conn.close = AsyncMock()

        with (
            patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn),
            patch("app.services.knowledge_manager.settings") as mock_settings,
            patch("app.services.knowledge_manager.embeddings_service") as mock_emb,
        ):
            mock_settings.embeddings_enabled = True
            mock_emb.embed_one = AsyncMock(return_value=[0.1] * 384)

            results = await manager.query_pgvector(pgvector_source, limit=5, query="relevant")

        assert len(results) == 1
        assert results[0]["id"] == "doc-1"
        assert results[0]["text"] == "relevant document"
        assert results[0]["score"] == pytest.approx(0.92)

        # Confirm the semantic SQL (with <=> operator) was used
        sql_arg = mock_conn.fetch.await_args.args[0]
        assert "<=>" in sql_arg

    @pytest.mark.asyncio
    async def test_query_pgvector_fallback_no_embedding(self, manager, pgvector_source):
        """When embeddings are disabled, query_pgvector falls back to recency scroll."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[{"id": "1", "text": "a doc", "metadata": None}]
        )
        mock_conn.close = AsyncMock()

        with (
            patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn),
            patch("app.services.knowledge_manager.settings") as mock_settings,
        ):
            mock_settings.embeddings_enabled = False

            results = await manager.query_pgvector(pgvector_source, limit=5)

        assert len(results) == 1
        assert results[0]["id"] == "1"
        # Confirm the fallback SQL (no vector operator) was used
        sql_arg = mock_conn.fetch.await_args.args[0]
        assert "<=>" not in sql_arg

    @pytest.mark.asyncio
    async def test_query_pgvector_fallback_no_query_string(
        self, manager, pgvector_source
    ):
        """When no query text is given (even if embeddings enabled), uses recency fallback."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[{"id": "2", "text": "doc", "metadata": {}}]
        )
        mock_conn.close = AsyncMock()

        with (
            patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn),
            patch("app.services.knowledge_manager.settings") as mock_settings,
        ):
            mock_settings.embeddings_enabled = True
            await manager.query_pgvector(pgvector_source, limit=3, query=None)

        sql_arg = mock_conn.fetch.await_args.args[0]
        assert "<=>" not in sql_arg

    @pytest.mark.asyncio
    async def test_query_pgvector_raises_when_no_dsn(self, manager):
        """query_pgvector raises ValueError when no DSN is configured."""
        source = MagicMock()
        source.connection_config = {"collection": "docs"}  # no dsn

        with pytest.raises(ValueError, match="[Nn][Oo].*[Dd][Ss][Nn]|[Dd][Ss][Nn].*not"):
            await manager.query_pgvector(source)

    @pytest.mark.asyncio
    async def test_query_pgvector_raises_when_no_collection(self, manager):
        """query_pgvector raises ValueError when no collection name is configured."""
        source = MagicMock()
        source.connection_config = {"dsn": "postgresql://localhost/db"}  # no collection

        with pytest.raises(ValueError, match="[Cc]ollection"):
            await manager.query_pgvector(source)


# ── KnowledgeSource enum / model tests ───────────────────────────────────────


class TestKnowledgeSourcePgvectorType:
    """Tests for the PGVECTOR member of KnowledgeSourceType."""

    def test_pgvector_in_enum(self):
        """KnowledgeSourceType.PGVECTOR has the expected string value."""
        assert KnowledgeSourceType.PGVECTOR == "pgvector"

    def test_pgvector_is_str_comparable(self):
        """KnowledgeSourceType members are StrEnum — string comparison works."""
        assert str(KnowledgeSourceType.PGVECTOR) == "pgvector"
        assert KnowledgeSourceType.PGVECTOR != "vector_db"
        assert KnowledgeSourceType.PGVECTOR != "mongo_db"

    def test_knowledge_source_accepts_pgvector_type(self):
        """KnowledgeSource can be constructed with source_type=PGVECTOR without error."""
        source = KnowledgeSource.model_construct(
            name="test-pgvector-source",
            source_type=KnowledgeSourceType.PGVECTOR,
            connection_config={
                "dsn": "postgresql://user:pass@localhost:5432/mydb",
                "collection": "documents",
            },
        )
        assert source.source_type == KnowledgeSourceType.PGVECTOR
        assert source.name == "test-pgvector-source"
        assert source.connection_config["collection"] == "documents"

    def test_knowledge_source_all_types_present(self):
        """KnowledgeSourceType has all three expected backends."""
        values = {t.value for t in KnowledgeSourceType}
        assert "vector_db" in values
        assert "mongo_db" in values
        assert "pgvector" in values
