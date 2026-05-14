"""Tests for the Memory system — models, schemas, service, routes, engine integration, and STM."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.memory import Memory, MemoryScope
from app.schemas.memory import (
    MemoryCreate,
    MemoryResponse,
    MemorySearchRequest,
    MemoryUpdate,
)

# ── Memory Model ─────────────────────────────────────────────────────────────


class TestMemoryModel:
    def test_memory_defaults(self):
        m = Memory.model_construct(
            agent_id="agent-1",
            scope=MemoryScope.AGENT,
            key="test-key",
            value="test-value",
        )
        assert m.agent_id == "agent-1"
        assert m.scope == MemoryScope.AGENT
        assert m.key == "test-key"
        assert m.value == "test-value"

    def test_memory_with_embedding(self):
        embedding = [0.1, 0.2, 0.3]
        m = Memory.model_construct(
            agent_id="agent-1",
            scope=MemoryScope.AGENT,
            key="embedded",
            value="some fact",
            embedding=embedding,
        )
        assert m.embedding == embedding

    def test_memory_with_ttl(self):
        ttl = datetime.now(UTC) + timedelta(hours=1)
        m = Memory.model_construct(
            agent_id="agent-1",
            scope=MemoryScope.SESSION,
            key="temp",
            value="temporary",
            ttl=ttl,
        )
        assert m.ttl == ttl

    def test_memory_metadata_default_empty(self):
        assert Memory.model_fields["metadata"].default_factory() == {}

    def test_memory_embedding_default_none(self):
        assert Memory.model_fields["embedding"].default is None

    def test_memory_ttl_default_none(self):
        assert Memory.model_fields["ttl"].default is None

    def test_scope_enum_values(self):
        assert MemoryScope.SESSION == "session"
        assert MemoryScope.AGENT == "agent"
        assert MemoryScope.GLOBAL == "global"

    def test_collection_name(self):
        assert Memory.Settings.name == "memories"


# ── Memory Schemas ───────────────────────────────────────────────────────────


class TestMemorySchemas:
    def test_memory_create_required_fields(self):
        body = MemoryCreate(
            agent_id="agent-1",
            scope=MemoryScope.AGENT,
            key="pref",
            value="dark mode",
        )
        assert body.agent_id == "agent-1"
        assert body.scope == MemoryScope.AGENT
        assert body.key == "pref"
        assert body.value == "dark mode"
        assert body.embedding is None
        assert body.metadata == {}
        assert body.ttl is None

    def test_memory_create_with_all_fields(self):
        ttl = datetime.now(UTC) + timedelta(hours=2)
        body = MemoryCreate(
            agent_id="agent-2",
            scope=MemoryScope.GLOBAL,
            key="fact",
            value="important info",
            embedding=[0.5, 0.6],
            metadata={"tags": ["important"]},
            ttl=ttl,
        )
        assert body.embedding == [0.5, 0.6]
        assert body.metadata == {"tags": ["important"]}
        assert body.ttl == ttl

    def test_memory_update_all_optional(self):
        body = MemoryUpdate()
        assert body.scope is None
        assert body.key is None
        assert body.value is None
        assert body.embedding is None
        assert body.metadata is None
        assert body.ttl is None

    def test_memory_update_partial(self):
        body = MemoryUpdate(value="updated value")
        assert body.value == "updated value"
        assert body.key is None

    def test_memory_response(self):
        now = datetime.now(UTC)
        resp = MemoryResponse(
            id="abc123",
            agent_id="agent-1",
            scope=MemoryScope.AGENT,
            key="pref",
            value="light mode",
            embedding=None,
            metadata={},
            ttl=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == "abc123"
        assert resp.scope == MemoryScope.AGENT

    def test_memory_search_request(self):
        req = MemorySearchRequest(
            agent_id="agent-1",
            query="preferences",
        )
        assert req.agent_id == "agent-1"
        assert req.query == "preferences"
        assert req.scope is None
        assert req.limit == 10

    def test_memory_search_request_with_scope(self):
        req = MemorySearchRequest(
            agent_id="agent-1",
            query="test",
            scope=MemoryScope.SESSION,
            limit=5,
        )
        assert req.scope == MemoryScope.SESSION
        assert req.limit == 5


# ── MemoryManager Service ───────────────────────────────────────────────────


class TestMemoryManager:
    @pytest.fixture()
    def manager(self):
        from app.services.memory_manager import MemoryManager
        return MemoryManager()

    @pytest.mark.asyncio
    async def test_store_new_memory(self, manager):
        mock_mem = MagicMock()
        mock_mem.key = "test-key"
        mock_mem.scope = MemoryScope.AGENT

        with (
            patch.object(Memory, "find_one", new_callable=AsyncMock, return_value=None),
            patch.object(Memory, "insert", new_callable=AsyncMock) as mock_insert,
        ):
            # Patch Memory constructor
            with (
                patch("app.services.memory_manager.Memory") as MockMemory,
                patch("app.services.memory_manager.memory_stm.push_memory", new_callable=AsyncMock),
                patch.object(manager, "_enforce_ltm_cap", new_callable=AsyncMock),
            ):
                instance = MagicMock()
                instance.insert = AsyncMock()
                instance.key = "test-key"
                instance.scope = MemoryScope.AGENT
                instance.value = "test-value"
                instance.updated_at = datetime.now(UTC)
                MockMemory.return_value = instance
                MockMemory.find_one = AsyncMock(return_value=None)

                result = await manager.store(
                    agent_id="agent-1",
                    scope=MemoryScope.AGENT,
                    key="test-key",
                    value="test-value",
                )
                assert result.key == "test-key"
                instance.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_upserts_existing(self, manager):
        existing = MagicMock()
        existing.set = AsyncMock()
        existing.key = "existing-key"
        existing.scope = MemoryScope.AGENT
        existing.value = "updated-value"
        existing.updated_at = datetime.now(UTC)

        with (
            patch("app.services.memory_manager.Memory") as MockMemory,
            patch("app.services.memory_manager.memory_stm.push_memory", new_callable=AsyncMock),
            patch.object(manager, "_enforce_ltm_cap", new_callable=AsyncMock),
        ):
            MockMemory.find_one = AsyncMock(return_value=existing)

            result = await manager.store(
                agent_id="agent-1",
                scope=MemoryScope.AGENT,
                key="existing-key",
                value="updated-value",
            )
            existing.set.assert_awaited_once()
            update_data = existing.set.call_args[0][0]
            assert update_data["value"] == "updated-value"
            assert "updated_at" in update_data

    @pytest.mark.asyncio
    async def test_retrieve(self, manager):
        mock_mem = MagicMock()
        mock_mem.key = "found"

        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find_one = AsyncMock(return_value=mock_mem)

            result = await manager.retrieve("agent-1", MemoryScope.AGENT, "found")
            assert result.key == "found"
            MockMemory.find_one.assert_awaited_once_with(
                {"agent_id": "agent-1", "scope": MemoryScope.AGENT, "key": "found"}
            )

    @pytest.mark.asyncio
    async def test_retrieve_not_found(self, manager):
        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find_one = AsyncMock(return_value=None)
            result = await manager.retrieve("agent-1", MemoryScope.AGENT, "missing")
            assert result is None

    @pytest.mark.asyncio
    async def test_search(self, manager):
        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.to_list = AsyncMock(return_value=[MagicMock(key="result-1")])

        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find.return_value = mock_chain

            results = await manager.search("agent-1", "test query", scope=MemoryScope.AGENT, limit=5)
            assert len(results) == 1

            # Verify filter includes scope and regex search
            call_args = MockMemory.find.call_args[0][0]
            assert call_args["agent_id"] == "agent-1"
            assert call_args["scope"] == MemoryScope.AGENT
            assert "$or" in call_args

    @pytest.mark.asyncio
    async def test_prune_expired(self, manager):
        mock_result = MagicMock()
        mock_result.deleted_count = 3

        mock_chain = MagicMock()
        mock_chain.delete = AsyncMock(return_value=mock_result)

        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find.return_value = mock_chain
            count = await manager.prune()
            assert count == 3

    @pytest.mark.asyncio
    async def test_prune_nothing_expired(self, manager):
        mock_result = MagicMock()
        mock_result.deleted_count = 0

        mock_chain = MagicMock()
        mock_chain.delete = AsyncMock(return_value=mock_result)

        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find.return_value = mock_chain
            count = await manager.prune()
            assert count == 0

    @pytest.mark.asyncio
    async def test_list_memories(self, manager):
        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.to_list = AsyncMock(return_value=[MagicMock(), MagicMock()])

        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find.return_value = mock_chain

            results = await manager.list_memories("agent-1", scope=MemoryScope.AGENT)
            assert len(results) == 2
            call_args = MockMemory.find.call_args[0][0]
            assert call_args["agent_id"] == "agent-1"
            assert call_args["scope"] == MemoryScope.AGENT

    @pytest.mark.asyncio
    async def test_list_memories_with_tags(self, manager):
        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.to_list = AsyncMock(return_value=[])

        with patch("app.services.memory_manager.Memory") as MockMemory:
            MockMemory.find.return_value = mock_chain

            await manager.list_memories("agent-1", tags=["important"])
            call_args = MockMemory.find.call_args[0][0]
            assert call_args["metadata.tags"] == {"$in": ["important"]}

    @pytest.mark.asyncio
    async def test_build_memory_context_empty(self, manager):
        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.to_list = AsyncMock(return_value=[])

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch("app.services.memory_manager.memory_stm.get_recent_memories", new_callable=AsyncMock, return_value=[]),
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_chain
            result = await manager.build_memory_context("agent-1")
            assert result == ""

    @pytest.mark.asyncio
    async def test_build_memory_context_from_stm(self, manager):
        """When STM has entries, they are used directly (no MongoDB fallback)."""
        stm_entries = [
            {"key": "pref", "scope": "agent", "value": "dark mode", "agent_id": "agent-1"},
        ]

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch("app.services.memory_manager.memory_stm.get_recent_memories", new_callable=AsyncMock, return_value=stm_entries),
        ):
            result = await manager.build_memory_context("agent-1")
            assert "<memories>" in result
            assert "dark mode" in result
            assert 'key="pref"' in result

    @pytest.mark.asyncio
    async def test_build_memory_context_fallback_to_ltm(self, manager):
        """When STM is empty, fall back to MongoDB LTM."""
        mem1 = MagicMock()
        mem1.key = "pref"
        mem1.scope = "agent"
        mem1.value = "dark mode"

        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.to_list = AsyncMock(side_effect=[[mem1], [], []])

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch("app.services.memory_manager.memory_stm.get_recent_memories", new_callable=AsyncMock, return_value=[]),
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_chain
            result = await manager.build_memory_context("agent-1", workflow_id="wf-1")
            assert "<memories>" in result
            assert "dark mode" in result
            assert 'key="pref"' in result

    @pytest.mark.asyncio
    async def test_build_memory_context_stm_failure_falls_back(self, manager):
        """When STM raises an exception, gracefully fall back to LTM."""
        mem1 = MagicMock()
        mem1.key = "fact"
        mem1.scope = "agent"
        mem1.value = "important"

        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.to_list = AsyncMock(side_effect=[[mem1], []])

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch("app.services.memory_manager.memory_stm.get_recent_memories", new_callable=AsyncMock, side_effect=ConnectionError("Redis down")),
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_chain
            result = await manager.build_memory_context("agent-1")
            assert "<memories>" in result
            assert "important" in result

    @pytest.mark.asyncio
    async def test_build_memory_context_dedupes_and_respects_budget(self, manager):
        stm_entries = [
            {"key": "pref", "scope": "agent", "value": "x" * 2000, "agent_id": "agent-1"},
            {"key": "pref", "scope": "agent", "value": "duplicate", "agent_id": "agent-1"},
            {"key": "fact", "scope": "global", "value": "useful", "agent_id": "agent-1"},
        ]

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch(
                "app.services.memory_manager.memory_stm.get_recent_memories",
                new_callable=AsyncMock,
                return_value=stm_entries,
            ),
        ):
            result = await manager.build_memory_context("agent-1", limit=10, max_chars=250)
            assert result.count('key="pref"') == 1
            assert len(result) <= 250
            assert "..." in result

    @pytest.mark.asyncio
    async def test_build_memory_context_uses_semantic_when_query_provided(self, manager):
        """When a query is provided and embeddings are enabled, semantic hits are used."""
        semantic_hits = [
            {"key": "semantic_fact", "scope": "agent", "value": "semantic match"},
        ]

        mock_qs = MagicMock()
        mock_qs.count = AsyncMock(return_value=1)

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch.object(manager, "search_semantic", new_callable=AsyncMock, return_value=semantic_hits) as mock_sem,
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_qs
            mock_settings.embeddings_enabled = True
            mock_settings.memory_retrieval_top_k = 8
            mock_settings.prompt_context_max_items = 12
            mock_settings.prompt_memory_char_budget = 4000
            mock_settings.prompt_context_item_char_limit = 1200
            result = await manager.build_memory_context("agent-1", query="find semantic fact")
            mock_sem.assert_awaited_once()
            assert "semantic match" in result

    @pytest.mark.asyncio
    async def test_build_memory_context_falls_back_to_stm_when_no_semantic_hits(self, manager):
        """When semantic search returns nothing, STM is used as fallback."""
        stm_entries = [{"key": "stm_key", "scope": "agent", "value": "stm_value"}]

        mock_qs = MagicMock()
        mock_qs.count = AsyncMock(return_value=1)

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch.object(manager, "search_semantic", new_callable=AsyncMock, return_value=[]),
            patch(
                "app.services.memory_manager.memory_stm.get_recent_memories",
                new_callable=AsyncMock,
                return_value=stm_entries,
            ),
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_qs
            mock_settings.embeddings_enabled = True
            mock_settings.memory_retrieval_top_k = 8
            mock_settings.prompt_context_max_items = 12
            mock_settings.prompt_memory_char_budget = 4000
            mock_settings.prompt_context_item_char_limit = 1200
            result = await manager.build_memory_context("agent-1", query="something")
            assert "stm_value" in result

    @pytest.mark.asyncio
    async def test_search_semantic_returns_empty_when_no_qdrant_url(self, manager):
        """search_semantic returns [] when qdrant_url is not configured."""
        with patch("app.services.memory_manager.settings") as mock_settings:
            mock_settings.qdrant_url = None
            mock_settings.embeddings_enabled = True
            result = await manager.search_semantic("agent-1", "any query")
            assert result == []

    @pytest.mark.asyncio
    async def test_search_semantic_returns_empty_when_embeddings_disabled(self, manager):
        """search_semantic returns [] when embeddings are disabled."""
        with patch("app.services.memory_manager.settings") as mock_settings:
            mock_settings.qdrant_url = "http://qdrant:6333"
            mock_settings.embeddings_enabled = False
            result = await manager.search_semantic("agent-1", "any query")
            assert result == []

    @pytest.mark.asyncio
    async def test_search_semantic_returns_empty_when_embed_fails(self, manager):
        """search_semantic returns [] when embedding generation fails."""
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
        ):
            mock_settings.qdrant_url = "http://qdrant:6333"
            mock_settings.embeddings_enabled = True
            mock_emb.embed_one = AsyncMock(return_value=None)
            result = await manager.search_semantic("agent-1", "any query")
            assert result == []

    @pytest.mark.asyncio
    async def test_store_auto_generates_embedding(self, manager):
        """store() should call embeddings_service.embed_one when no embedding is supplied."""
        with (
            patch("app.services.memory_manager.settings") as mock_settings,
            patch("app.services.memory_manager.embeddings_service") as mock_emb,
            patch("app.services.memory_manager.Memory") as MockMemory,
            patch("app.services.memory_manager.memory_stm.push_memory", new_callable=AsyncMock),
            patch.object(manager, "_enforce_ltm_cap", new_callable=AsyncMock),
            patch.object(manager, "_upsert_vector_store", new_callable=AsyncMock),
        ):
            mock_settings.embeddings_enabled = True
            mock_emb.embed_one = AsyncMock(return_value=[0.1, 0.2, 0.3])

            instance = MagicMock()
            instance.insert = AsyncMock()
            instance.key = "k"
            instance.scope = MemoryScope.AGENT
            instance.value = "v"
            instance.updated_at = datetime.now(UTC)
            MockMemory.return_value = instance
            MockMemory.find_one = AsyncMock(return_value=None)

            await manager.store("agent-1", MemoryScope.AGENT, "k", "v")
            mock_emb.embed_one.assert_awaited_once_with("k: v")


# ── Memory Routes ────────────────────────────────────────────────────────────


class TestMemoryRoutes:
    @pytest.fixture()
    def client(self, app_client):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides[get_current_user] = lambda: {"login": "testuser"}
        yield app_client
        app.dependency_overrides.pop(get_current_user, None)

    def test_create_memory(self, client):
        mock_mem = MagicMock()
        mock_mem.id = "mem-id-1"
        mock_mem.agent_id = "agent-1"
        mock_mem.scope = MemoryScope.AGENT
        mock_mem.key = "test-key"
        mock_mem.value = "test-value"
        mock_mem.embedding = None
        mock_mem.metadata = {}
        mock_mem.ttl = None
        mock_mem.created_at = datetime.now(UTC)
        mock_mem.updated_at = datetime.now(UTC)

        with patch(
            "app.api.routes.memories.memory_manager.store",
            new_callable=AsyncMock,
            return_value=mock_mem,
        ):
            resp = client.post("/api/memories", json={
                "agent_id": "agent-1",
                "scope": "agent",
                "key": "test-key",
                "value": "test-value",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["id"] == "mem-id-1"
            assert data["key"] == "test-key"

    def test_get_memory(self, client):
        mock_mem = MagicMock()
        mock_mem.id = "mem-id-1"
        mock_mem.agent_id = "agent-1"
        mock_mem.scope = MemoryScope.AGENT
        mock_mem.key = "test-key"
        mock_mem.value = "test-value"
        mock_mem.embedding = None
        mock_mem.metadata = {}
        mock_mem.ttl = None
        mock_mem.created_at = datetime.now(UTC)
        mock_mem.updated_at = datetime.now(UTC)

        with patch(
            "app.api.routes.memories.Memory.get",
            new_callable=AsyncMock,
            return_value=mock_mem,
        ):
            resp = client.get("/api/memories/6601a1b2c3d4e5f607890abc")
            assert resp.status_code == 200
            assert resp.json()["key"] == "test-key"

    def test_get_memory_not_found(self, client):
        with patch(
            "app.api.routes.memories.Memory.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/memories/6601a1b2c3d4e5f607890abc")
            assert resp.status_code == 404

    def test_delete_memory(self, client):
        mock_mem = MagicMock()
        mock_mem.delete = AsyncMock()

        with patch(
            "app.api.routes.memories.Memory.get",
            new_callable=AsyncMock,
            return_value=mock_mem,
        ):
            resp = client.delete("/api/memories/6601a1b2c3d4e5f607890abc")
            assert resp.status_code == 204

    def test_delete_memory_not_found(self, client):
        with patch(
            "app.api.routes.memories.Memory.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.delete("/api/memories/6601a1b2c3d4e5f607890abc")
            assert resp.status_code == 404

    def test_search_memories(self, client):
        mock_mem = MagicMock()
        mock_mem.id = "mem-id-1"
        mock_mem.agent_id = "agent-1"
        mock_mem.scope = MemoryScope.AGENT
        mock_mem.key = "pref"
        mock_mem.value = "dark mode"
        mock_mem.embedding = None
        mock_mem.metadata = {}
        mock_mem.ttl = None
        mock_mem.created_at = datetime.now(UTC)
        mock_mem.updated_at = datetime.now(UTC)

        with patch(
            "app.api.routes.memories.memory_manager.search",
            new_callable=AsyncMock,
            return_value=[mock_mem],
        ):
            resp = client.post("/api/memories/search", json={
                "agent_id": "agent-1",
                "query": "mode",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["key"] == "pref"

    def test_get_stm_memories(self, client):
        stm_entries = [
            {"key": "user_name", "scope": "session", "value": "Alice",
             "updated_at": "2025-01-01T00:00:00Z"},
            {"key": "pref", "scope": "agent", "value": "dark mode",
             "updated_at": "2025-01-01T00:00:00Z"},
        ]
        with patch(
            "app.api.routes.memories.memory_stm.get_recent_memories",
            new_callable=AsyncMock,
            return_value=stm_entries,
        ):
            resp = client.get("/api/memories/stm/agent-1")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert data[0]["key"] == "user_name"

    def test_get_stm_memories_empty(self, client):
        with patch(
            "app.api.routes.memories.memory_stm.get_recent_memories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/api/memories/stm/agent-1")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_get_stm_memories_redis_error(self, client):
        with patch(
            "app.api.routes.memories.memory_stm.get_recent_memories",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            resp = client.get("/api/memories/stm/agent-1")
            assert resp.status_code == 200
            assert resp.json() == []


# ── store_memory tool handler ────────────────────────────────────────────────


class TestStoreMemoryHandler:
    @pytest.mark.asyncio
    async def test_handle_store_memory_success(self):
        from app.core.agent_engine import _handle_store_memory

        mock_mem = MagicMock()
        mock_mem.key = "fact"
        mock_mem.scope = "agent"

        with patch(
            "app.core.agent_engine.memory_manager.store",
            new_callable=AsyncMock,
            return_value=mock_mem,
        ):
            result = await _handle_store_memory("agent-1", {
                "key": "fact",
                "value": "The sky is blue",
                "scope": "agent",
            })
            data = json.loads(result)
            assert data["status"] == "stored"
            assert data["key"] == "fact"

    @pytest.mark.asyncio
    async def test_handle_store_memory_missing_key(self):
        from app.core.agent_engine import _handle_store_memory

        result = await _handle_store_memory("agent-1", {"value": "something"})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_handle_store_memory_missing_value(self):
        from app.core.agent_engine import _handle_store_memory

        result = await _handle_store_memory("agent-1", {"key": "test"})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_handle_store_memory_invalid_scope(self):
        from app.core.agent_engine import _handle_store_memory

        result = await _handle_store_memory("agent-1", {
            "key": "test",
            "value": "val",
            "scope": "invalid",
        })
        data = json.loads(result)
        assert "error" in data
        assert "Invalid scope" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_store_memory_default_scope(self):
        from app.core.agent_engine import _handle_store_memory

        mock_mem = MagicMock()
        mock_mem.key = "fact"
        mock_mem.scope = "agent"

        with patch(
            "app.core.agent_engine.memory_manager.store",
            new_callable=AsyncMock,
            return_value=mock_mem,
        ) as mock_store:
            await _handle_store_memory("agent-1", {
                "key": "fact",
                "value": "something",
            })
            # Default scope should be "agent"
            call_kwargs = mock_store.call_args
            assert call_kwargs[1]["scope"].value == "agent" or str(call_kwargs[1]["scope"]) == "agent"


class TestStoreMemoryLogging:
    @pytest.mark.asyncio
    async def test_log_store_memory_result_success(self):
        from app.core.agent_engine import _log_store_memory_result

        workflow = MagicMock()
        task_exec = MagicMock()

        with patch("app.core.agent_engine._log", new_callable=AsyncMock) as mock_log:
            await _log_store_memory_result(
                workflow,
                task_exec,
                json.dumps({"status": "stored", "key": "fact", "scope": "agent"}),
            )

        mock_log.assert_awaited_once()
        args = mock_log.await_args.args
        assert args[1] == "memory_stored"
        assert args[2] == "key=fact scope=agent"

    @pytest.mark.asyncio
    async def test_log_store_memory_result_failure(self):
        from app.core.agent_engine import _log_store_memory_result

        workflow = MagicMock()
        task_exec = MagicMock()

        with patch("app.core.agent_engine._log", new_callable=AsyncMock) as mock_log:
            await _log_store_memory_result(
                workflow,
                task_exec,
                json.dumps({"error": "Both 'key' and 'value' are required"}),
            )

        mock_log.assert_awaited_once()
        args = mock_log.await_args.args
        assert args[1] == "memory_store_failed"
        assert "required" in args[2]

    @pytest.mark.asyncio
    async def test_log_store_memory_result_invalid_payload(self):
        from app.core.agent_engine import _log_store_memory_result

        workflow = MagicMock()
        task_exec = MagicMock()

        with patch("app.core.agent_engine._log", new_callable=AsyncMock) as mock_log:
            await _log_store_memory_result(workflow, task_exec, "not-json")

        mock_log.assert_awaited_once()
        args = mock_log.await_args.args
        assert args[1] == "memory_store_failed"
        assert "non-JSON" in args[2]


# ── STM (Short-Term Memory) ─────────────────────────────────────────────────


class TestMemorySTM:
    """Tests for the Redis-backed Short-Term Memory layer."""

    @pytest.mark.asyncio
    async def test_push_and_get_recent(self):
        from app.services import memory_stm

        mock_redis = AsyncMock()
        mock_redis.zrange = AsyncMock(return_value=[])
        mock_redis.zadd = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=1)
        mock_redis.zrevrange = AsyncMock(return_value=[
            json.dumps({"scope": "agent", "key": "k1", "value": "v1", "agent_id": "a1"}),
        ])

        with patch("app.services.memory_stm._get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await memory_stm.push_memory("a1", {
                "scope": "agent", "key": "k1", "value": "v1",
                "agent_id": "a1", "updated_at": datetime.now(UTC).isoformat(),
            })
            mock_redis.zadd.assert_awaited_once()

            result = await memory_stm.get_recent_memories("a1")
            assert len(result) == 1
            assert result[0]["key"] == "k1"

    @pytest.mark.asyncio
    async def test_push_deduplicates_by_scope_key(self):
        from app.services import memory_stm

        existing_entry = json.dumps({"scope": "agent", "key": "k1", "value": "old"})
        mock_redis = AsyncMock()
        mock_redis.zrange = AsyncMock(return_value=[existing_entry])
        mock_redis.zrem = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=1)

        with patch("app.services.memory_stm._get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await memory_stm.push_memory("a1", {
                "scope": "agent", "key": "k1", "value": "new",
                "agent_id": "a1", "updated_at": datetime.now(UTC).isoformat(),
            })
            # Should have removed old entry
            mock_redis.zrem.assert_awaited_once_with("stm:a1", existing_entry)
            mock_redis.zadd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_push_trims_to_max_entries(self):
        from app.services import memory_stm

        mock_redis = AsyncMock()
        mock_redis.zrange = AsyncMock(return_value=[])
        mock_redis.zadd = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=25)
        mock_redis.zremrangebyrank = AsyncMock()

        with (
            patch("app.services.memory_stm._get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.services.memory_stm.settings") as mock_settings,
        ):
            mock_settings.stm_max_entries = 20
            await memory_stm.push_memory("a1", {
                "scope": "agent", "key": "new", "value": "v",
                "agent_id": "a1", "updated_at": datetime.now(UTC).isoformat(),
            })
            # Should trim oldest 5 entries (25 - 20)
            mock_redis.zremrangebyrank.assert_awaited_once_with("stm:a1", 0, 4)

    @pytest.mark.asyncio
    async def test_remove_memory(self):
        from app.services import memory_stm

        entry = json.dumps({"scope": "agent", "key": "k1", "value": "v1"})
        mock_redis = AsyncMock()
        mock_redis.zrange = AsyncMock(return_value=[entry])
        mock_redis.zrem = AsyncMock()

        with patch("app.services.memory_stm._get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await memory_stm.remove_memory("a1", "agent", "k1")
            mock_redis.zrem.assert_awaited_once_with("stm:a1", entry)

    @pytest.mark.asyncio
    async def test_clear_agent_stm(self):
        from app.services import memory_stm

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch("app.services.memory_stm._get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await memory_stm.clear_agent_stm("a1")
            mock_redis.delete.assert_awaited_once_with("stm:a1")

    @pytest.mark.asyncio
    async def test_warmup_all_agents(self):
        from app.services import memory_stm

        now = datetime.now(UTC)
        mock_groups = [
            {
                "_id": "agent-1",
                "memories": [
                    {"scope": "agent", "key": "k1", "value": "v1", "updated_at": now},
                    {"scope": "agent", "key": "k2", "value": "v2", "updated_at": now},
                ],
            },
            {
                "_id": "agent-2",
                "memories": [
                    {"scope": "global", "key": "g1", "value": "gv1", "updated_at": now},
                ],
            },
        ]

        async def _async_iter():
            for g in mock_groups:
                yield g

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = _async_iter()

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=2)

        with (
            patch("app.models.memory.Memory.get_motor_collection", return_value=mock_collection),
            patch("app.services.memory_stm._get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.services.memory_stm.settings") as mock_settings,
        ):
            mock_settings.stm_max_entries = 20
            count = await memory_stm.warmup_all_agents()
            assert count == 2
            # Two agents should each have their STM cleared and populated
            assert mock_redis.delete.await_count == 2
            assert mock_redis.zadd.await_count == 2


# ── LTM Cap Enforcement ─────────────────────────────────────────────────────


class TestLTMCapEnforcement:
    @pytest.fixture()
    def manager(self):
        from app.services.memory_manager import MemoryManager
        return MemoryManager()

    @pytest.mark.asyncio
    async def test_enforce_ltm_cap_removes_oldest(self, manager):
        mock_chain = MagicMock()
        mock_chain.count = AsyncMock(return_value=210)
        mock_chain.sort.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        old_mem1 = MagicMock()
        old_mem1.delete = AsyncMock()
        old_mem2 = MagicMock()
        old_mem2.delete = AsyncMock()
        mock_chain.to_list = AsyncMock(return_value=[old_mem1, old_mem2])

        with (
            patch("app.services.memory_manager.Memory") as MockMemory,
            patch("app.services.memory_manager.settings") as mock_settings,
        ):
            MockMemory.find.return_value = mock_chain
            mock_settings.ltm_max_entries = 200
            await manager._enforce_ltm_cap("agent-1")
            old_mem1.delete.assert_awaited_once()
            old_mem2.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enforce_ltm_cap_no_action_under_limit(self, manager):
        mock_chain = MagicMock()
        mock_chain.count = AsyncMock(return_value=50)

        with (
            patch("app.services.memory_manager.Memory") as MockMemory,
            patch("app.services.memory_manager.settings") as mock_settings,
        ):
            MockMemory.find.return_value = mock_chain
            mock_settings.ltm_max_entries = 200
            await manager._enforce_ltm_cap("agent-1")
            # No sort/limit/to_list should be called
            mock_chain.sort.assert_not_called()

    @pytest.mark.asyncio
    async def test_enforce_ltm_cap_unlimited(self, manager):
        """When ltm_max_entries=0, no capping is performed."""
        with patch("app.services.memory_manager.settings") as mock_settings:
            mock_settings.ltm_max_entries = 0
            await manager._enforce_ltm_cap("agent-1")
            # Should return immediately — no Memory.find call
