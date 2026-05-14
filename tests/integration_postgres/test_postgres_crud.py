"""PostgreSQL integration tests: CRUD operations.

Exercises the full PostgresDocument stack against a real PostgreSQL database.
Tests cover: insert, get, find_one, find, update (save/set), delete, and
ordering/filtering on every model type used by the application.

Run with:
    DB_BACKEND=postgres \\
      TEST_POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5433/tbd_agents_integration_test \\
      pytest tests/integration/postgres/test_postgres_crud.py -v
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from .conftest import create_agent, create_skill, create_task, create_workflow


# ===========================================================================
# Agent CRUD
# ===========================================================================


class TestAgentCRUD:
    """Full CRUD cycle for the Agent model."""

    @pytest.mark.asyncio
    async def test_insert_and_get(self):
        """Inserted agent is retrievable by ID."""
        from app.models.agent import Agent

        agent = await create_agent(name="test-crud-agent")
        assert agent.id is not None

        fetched = await Agent.get(agent.id)
        assert fetched is not None
        assert fetched.name == "test-crud-agent"
        assert fetched.id == agent.id

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        """Agent.get() returns None for a non-existent ID."""
        from app.models.agent import Agent

        result = await Agent.get("00000000-0000-0000-0000-000000000000")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_one_by_field(self):
        """find_one() with a field filter returns the matching document."""
        from app.models.agent import Agent

        await create_agent(name="findable-agent")
        await create_agent(name="other-agent")

        result = await Agent.find_one({"name": "findable-agent"})
        assert result is not None
        assert result.name == "findable-agent"

    @pytest.mark.asyncio
    async def test_find_all(self):
        """find_all() returns all inserted agents."""
        from app.models.agent import Agent

        await create_agent(name="agent-a")
        await create_agent(name="agent-b")
        await create_agent(name="agent-c")

        agents = await Agent.find_all().to_list()
        assert len(agents) == 3
        names = {a.name for a in agents}
        assert names == {"agent-a", "agent-b", "agent-c"}

    @pytest.mark.asyncio
    async def test_find_with_filter(self):
        """find() with a filter returns only matching documents."""
        from app.models.agent import Agent

        await create_agent(name="alpha")
        await create_agent(name="beta")

        results = await Agent.find({"name": "alpha"}).to_list()
        assert len(results) == 1
        assert results[0].name == "alpha"

    @pytest.mark.asyncio
    async def test_save_updates_existing(self):
        """save() on an existing document updates it in-place."""
        from app.models.agent import Agent

        agent = await create_agent(name="original-name")
        agent.name = "updated-name"
        await agent.save()

        fetched = await Agent.get(agent.id)
        assert fetched.name == "updated-name"

    @pytest.mark.asyncio
    async def test_set_partial_update(self):
        """set() applies a partial update dict without touching other fields."""
        from app.models.agent import Agent

        agent = await create_agent(name="before-set", description="keep-me")
        await agent.set({"name": "after-set"})

        fetched = await Agent.get(agent.id)
        assert fetched.name == "after-set"
        assert fetched.description == "keep-me"

    @pytest.mark.asyncio
    async def test_delete(self):
        """delete() removes the document from the database."""
        from app.models.agent import Agent

        agent = await create_agent(name="to-delete")
        await agent.delete()

        fetched = await Agent.get(agent.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_ids_are_uuids(self):
        """Auto-generated IDs are valid UUID strings."""
        import uuid

        agent = await create_agent()
        # Should not raise
        uuid.UUID(agent.id)

    @pytest.mark.asyncio
    async def test_upsert_with_explicit_id(self):
        """An agent inserted with an explicit ID can be fetched by that ID."""
        from app.models.agent import Agent
        import uuid

        explicit_id = str(uuid.uuid4())
        agent = await create_agent(id=explicit_id, name="explicit-id-agent")
        assert agent.id == explicit_id

        fetched = await Agent.get(explicit_id)
        assert fetched is not None
        assert fetched.name == "explicit-id-agent"

    @pytest.mark.asyncio
    async def test_array_field_persisted_correctly(self):
        """Array fields (mcp_server_ids) survive a round-trip."""
        from app.models.agent import Agent

        agent = await create_agent(
            mcp_server_ids=["mcp-a", "mcp-b"],
        )
        fetched = await Agent.get(agent.id)
        assert fetched.mcp_server_ids == ["mcp-a", "mcp-b"]

    @pytest.mark.asyncio
    async def test_count(self):
        """PgQuerySet.count() returns the number of matching documents."""
        from app.models.agent import Agent

        await create_agent(name="count-a")
        await create_agent(name="count-b")

        total = await Agent.find_all().count()
        assert total == 2

    @pytest.mark.asyncio
    async def test_limit_and_skip(self):
        """limit() and skip() respect pagination."""
        from app.models.agent import Agent

        for i in range(5):
            await create_agent(name=f"paged-{i}")

        page_1 = await Agent.find_all().sort("name").limit(2).to_list()
        page_2 = await Agent.find_all().sort("name").skip(2).limit(2).to_list()

        assert len(page_1) == 2
        assert len(page_2) == 2
        # No overlap
        ids_1 = {a.id for a in page_1}
        ids_2 = {a.id for a in page_2}
        assert ids_1.isdisjoint(ids_2)

    @pytest.mark.asyncio
    async def test_created_at_set_on_insert(self):
        """created_at is automatically set on first insert."""
        from app.models.agent import Agent

        before = datetime.now(UTC)
        agent = await create_agent()
        after = datetime.now(UTC)

        fetched = await Agent.get(agent.id)
        assert fetched.created_at is not None
        assert before <= fetched.created_at <= after

    @pytest.mark.asyncio
    async def test_updated_at_changes_on_save(self):
        """updated_at is refreshed on each save() call."""
        from app.models.agent import Agent
        import asyncio

        agent = await create_agent(name="update-ts-test")
        original_updated = (await Agent.get(agent.id)).updated_at

        await asyncio.sleep(0.05)  # ensure time advances
        agent.description = "changed"
        await agent.save()

        refetched = await Agent.get(agent.id)
        assert refetched.updated_at > original_updated


# ===========================================================================
# Workflow CRUD — includes JSONB (messages, logs) and enum (status) fields
# ===========================================================================


class TestWorkflowCRUD:
    """CRUD tests for Workflow, focusing on complex field types."""

    @pytest.mark.asyncio
    async def test_insert_and_get(self):
        """Workflow is insertable and retrievable with correct defaults."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)

        fetched = await Workflow.get(wf.id)
        assert fetched is not None
        assert fetched.agent_id == str(agent.id)
        assert fetched.status == WorkflowStatus.ACTIVE
        assert fetched.messages == []
        assert fetched.logs == []
        assert fetched.current_turn == 0

    @pytest.mark.asyncio
    async def test_jsonb_messages_round_trip(self):
        """JSONB messages list survives a full DB round-trip."""
        from app.models.workflow import Message, Workflow

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.messages = [
            Message(role="user", content="Hello, world!"),
            Message(role="assistant", content="Hi there!"),
        ]
        await wf.save()

        fetched = await Workflow.get(wf.id)
        assert len(fetched.messages) == 2
        assert fetched.messages[0].role == "user"
        assert fetched.messages[0].content == "Hello, world!"
        assert fetched.messages[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_enum_status_round_trip(self):
        """WorkflowStatus enum values persist and deserialise correctly."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = WorkflowStatus.RUNNING
        await wf.save()

        fetched = await Workflow.get(wf.id)
        assert fetched.status == WorkflowStatus.RUNNING

    @pytest.mark.asyncio
    async def test_find_by_agent_id(self):
        """find() filters workflows by agent_id correctly."""
        from app.models.workflow import Workflow

        agent_a = await create_agent(name="agent-a")
        agent_b = await create_agent(name="agent-b")
        await create_workflow(agent_a)
        await create_workflow(agent_a)
        await create_workflow(agent_b)

        wfs_a = await Workflow.find({"agent_id": str(agent_a.id)}).to_list()
        assert len(wfs_a) == 2
        for wf in wfs_a:
            assert wf.agent_id == str(agent_a.id)

    @pytest.mark.asyncio
    async def test_usage_stats_jsonb(self):
        """UsageStats nested model persists as JSONB correctly."""
        from app.models.workflow import UsageStats, Workflow

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.usage = UsageStats(
            total_input_tokens=1000,
            total_output_tokens=500,
            total_cost=0.05,
        )
        await wf.save()

        fetched = await Workflow.get(wf.id)
        assert fetched.usage is not None
        assert fetched.usage.total_input_tokens == 1000
        assert fetched.usage.total_output_tokens == 500
        assert abs(fetched.usage.total_cost - 0.05) < 1e-9


# ===========================================================================
# TaskExecution CRUD — nested models, datetime fields
# ===========================================================================


class TestTaskExecutionCRUD:
    """CRUD tests for TaskExecution."""

    @pytest.mark.asyncio
    async def test_insert_and_get(self):
        """TaskExecution is insertable and retrievable."""
        from app.models.task_execution import TaskExecution, TaskStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf, prompt="What is 2+2?")

        fetched = await TaskExecution.get(task.id)
        assert fetched is not None
        assert fetched.prompt == "What is 2+2?"
        assert fetched.status == TaskStatus.PENDING
        assert fetched.workflow_id == str(wf.id)

    @pytest.mark.asyncio
    async def test_status_transitions(self):
        """TaskExecution status field transitions persist correctly."""
        from app.models.task_execution import TaskExecution, TaskStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf)

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(UTC)
        await task.save()

        task.status = TaskStatus.COMPLETED
        task.finished_at = datetime.now(UTC)
        task.response = "The answer is 42"
        await task.save()

        fetched = await TaskExecution.get(task.id)
        assert fetched.status == TaskStatus.COMPLETED
        assert fetched.response == "The answer is 42"
        assert fetched.started_at is not None
        assert fetched.finished_at is not None
        assert fetched.finished_at >= fetched.started_at

    @pytest.mark.asyncio
    async def test_find_by_workflow_id(self):
        """find() filters tasks by workflow_id."""
        from app.models.task_execution import TaskExecution

        agent = await create_agent()
        wf_a = await create_workflow(agent)
        wf_b = await create_workflow(agent)
        await create_task(wf_a, prompt="task 1")
        await create_task(wf_a, prompt="task 2")
        await create_task(wf_b, prompt="task 3")

        tasks_a = await TaskExecution.find({"workflow_id": str(wf_a.id)}).to_list()
        assert len(tasks_a) == 2
        assert all(t.workflow_id == str(wf_a.id) for t in tasks_a)

    @pytest.mark.asyncio
    async def test_worker_field_stored(self):
        """The worker hostname field persists correctly."""
        from app.models.task_execution import TaskExecution

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf)
        task.worker = "celery@worker-1"
        await task.save()

        fetched = await TaskExecution.get(task.id)
        assert fetched.worker == "celery@worker-1"

    @pytest.mark.asyncio
    async def test_logs_jsonb_array(self):
        """Logs list (JSONB array of LogEntry) survives a round-trip."""
        from app.models.task_execution import TaskExecution
        from app.models.workflow import LogEntry

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf)
        task.logs = [
            LogEntry(event="provider_resolved", detail="Using openai"),
            LogEntry(event="completed", detail="Done"),
        ]
        await task.save()

        fetched = await TaskExecution.get(task.id)
        assert len(fetched.logs) == 2
        assert fetched.logs[0].event == "provider_resolved"
        assert fetched.logs[1].event == "completed"

    @pytest.mark.asyncio
    async def test_delete_task(self):
        """delete() removes the TaskExecution from the database."""
        from app.models.task_execution import TaskExecution

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf)

        await task.delete()
        assert await TaskExecution.get(task.id) is None


# ===========================================================================
# PgQuerySet advanced operations
# ===========================================================================


class TestPgQuerySetAdvanced:
    """Tests for PgQuerySet sorting, limiting, counting, and filtering."""

    @pytest.mark.asyncio
    async def test_sort_descending(self):
        """sort() with '-field' syntax returns results in descending order."""
        import asyncio
        from app.models.task_execution import TaskExecution

        agent = await create_agent()
        wf = await create_workflow(agent)
        for i in range(3):
            task = await create_task(wf, prompt=f"task-{i}")
            await asyncio.sleep(0.02)  # ensure distinct created_at
            _ = task

        tasks = await TaskExecution.find_all().sort("-created_at").to_list()
        for i in range(len(tasks) - 1):
            assert tasks[i].created_at >= tasks[i + 1].created_at

    @pytest.mark.asyncio
    async def test_count_with_filter(self):
        """count() with a filter returns the correct number."""
        from app.models.task_execution import TaskExecution, TaskStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        await create_task(wf, status=TaskStatus.PENDING)
        await create_task(wf, status=TaskStatus.PENDING)
        await create_task(wf, status=TaskStatus.COMPLETED)

        pending_count = await TaskExecution.find({"status": TaskStatus.PENDING}).count()
        assert pending_count == 2

    @pytest.mark.asyncio
    async def test_none_filter_produces_is_null(self):
        """Filtering by None generates IS NULL and matches null-field rows."""
        from app.models.task_execution import TaskExecution

        agent = await create_agent()
        wf = await create_workflow(agent)
        task_no_worker = await create_task(wf, prompt="no-worker")
        task_with_worker = await create_task(wf, prompt="with-worker")
        task_with_worker.worker = "worker-1"
        await task_with_worker.save()

        results = await TaskExecution.find({"worker": None}).to_list()
        ids = {t.id for t in results}
        assert task_no_worker.id in ids
        assert task_with_worker.id not in ids

    @pytest.mark.asyncio
    async def test_first(self):
        """first() returns one document or None when empty."""
        from app.models.agent import Agent

        result = await Agent.find_all().first()
        assert result is None

        await create_agent(name="solo-agent")
        result = await Agent.find_all().first()
        assert result is not None
        assert result.name == "solo-agent"
