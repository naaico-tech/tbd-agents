"""Tests for the Memory system — models, schemas, service, routes, and engine integration."""

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
            with patch("app.services.memory_manager.Memory") as MockMemory:
                instance = MagicMock()
                instance.insert = AsyncMock()
                instance.key = "test-key"
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

        with patch("app.services.memory_manager.Memory") as MockMemory:
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
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_chain
            result = await manager.build_memory_context("agent-1")
            assert result == ""

    @pytest.mark.asyncio
    async def test_build_memory_context_with_memories(self, manager):
        mem1 = MagicMock()
        mem1.key = "pref"
        mem1.scope = "agent"
        mem1.value = "dark mode"

        mock_chain = MagicMock()
        mock_chain.sort.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        # Agent-scope returns mem1, global and session return empty
        mock_chain.to_list = AsyncMock(side_effect=[[mem1], [], []])

        with (
            patch.object(manager, "prune", new_callable=AsyncMock),
            patch("app.services.memory_manager.Memory") as MockMemory,
        ):
            MockMemory.find.return_value = mock_chain
            result = await manager.build_memory_context("agent-1", workflow_id="wf-1")
            assert "<memories>" in result
            assert "dark mode" in result
            assert 'key="pref"' in result


# ── Memory Routes ────────────────────────────────────────────────────────────


class TestMemoryRoutes:
    @pytest.fixture()
    def _auth(self):
        with patch(
            "app.api.deps.get_current_user",
            return_value={"login": "testuser"},
        ):
            yield

    @pytest.fixture()
    def client(self, app_client, _auth):
        return app_client

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
