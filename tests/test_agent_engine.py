"""Tests for the agent_engine helper functions."""

import json

import pytest

from app.core.agent_engine import _parse_todo_list
from app.models.task_execution import TaskProgress, TodoItemStatus


class TestParseTodoList:
    def test_valid_todo_list(self):
        args = {
            "todoList": [
                {"id": 1, "title": "Step 1", "status": "completed"},
                {"id": 2, "title": "Step 2", "status": "in-progress"},
                {"id": 3, "title": "Step 3", "status": "not-started"},
            ]
        }
        result = _parse_todo_list(args)
        assert result is not None
        assert len(result.todos) == 3
        assert result.current_step == 2
        assert result.percent_complete == round(1 / 3, 2)

    def test_all_completed(self):
        args = {
            "todoList": [
                {"id": 1, "title": "Done 1", "status": "completed"},
                {"id": 2, "title": "Done 2", "status": "completed"},
            ]
        }
        result = _parse_todo_list(args)
        assert result is not None
        assert result.percent_complete == 1.0
        assert result.current_step is None

    def test_empty_todo_list(self):
        result = _parse_todo_list({"todoList": []})
        assert result is None

    def test_no_todo_list_key(self):
        result = _parse_todo_list({"other": "data"})
        assert result is None

    def test_string_input(self):
        args_str = json.dumps({
            "todoList": [
                {"id": 1, "title": "Task", "status": "not-started"},
            ]
        })
        result = _parse_todo_list(args_str)
        assert result is not None
        assert len(result.todos) == 1

    def test_invalid_json_string(self):
        result = _parse_todo_list("not-json")
        assert result is None

    def test_invalid_status_defaults(self):
        args = {
            "todoList": [
                {"id": 1, "title": "Task", "status": "unknown-status"},
            ]
        }
        result = _parse_todo_list(args)
        assert result is not None
        assert result.todos[0].status == TodoItemStatus.NOT_STARTED

    def test_missing_fields_use_defaults(self):
        args = {
            "todoList": [
                {"id": 1, "title": "Task"},
            ]
        }
        result = _parse_todo_list(args)
        assert result is not None
        assert result.todos[0].status == TodoItemStatus.NOT_STARTED

    def test_list_input_ignored(self):
        result = _parse_todo_list([1, 2, 3])
        assert result is None


# ── Auto-memory extraction tests ─────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.agent_engine import _extract_auto_memories
from app.models.workflow import Message, Workflow


class TestExtractAutoMemories:
    """Test the _extract_auto_memories helper function."""

    @pytest.fixture
    def mock_workflow(self):
        wf = MagicMock(spec=Workflow)
        wf.id = "wf-123"
        wf.model = "gpt-4.1"
        wf.messages = [
            Message(role="user", content="What's the weather in Paris?"),
            Message(role="assistant", content="The weather in Paris is 18°C and sunny. User prefers Celsius."),
        ]
        return wf

    @pytest.mark.asyncio
    async def test_extracts_new_memories(self, mock_workflow):
        """Should extract and store new memories from conversation."""
        llm_response = json.dumps([
            {"key": "user_prefers_celsius", "value": "User prefers Celsius temperature units"},
        ])

        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine.memory_manager") as mock_mm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, return_value=llm_response):
            mock_stm.get_recent_memories = AsyncMock(return_value=[])
            mock_mm.store = AsyncMock(return_value=MagicMock(key="user_prefers_celsius", scope="agent"))

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 1
            mock_mm.store.assert_called_once()
            call_kwargs = mock_mm.store.call_args.kwargs
            assert call_kwargs["key"] == "user_prefers_celsius"
            assert call_kwargs["metadata"]["source"] == "auto_memory"

    @pytest.mark.asyncio
    async def test_deduplicates_against_stm(self, mock_workflow):
        """Should skip memories whose keys already exist in STM."""
        llm_response = json.dumps([
            {"key": "existing_memory", "value": "This already exists"},
            {"key": "new_memory", "value": "This is new"},
        ])

        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine.memory_manager") as mock_mm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, return_value=llm_response):
            mock_stm.get_recent_memories = AsyncMock(return_value=[
                {"key": "existing_memory", "value": "Already stored"},
            ])
            mock_mm.store = AsyncMock(return_value=MagicMock(key="new_memory", scope="agent"))

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 1
            mock_mm.store.assert_called_once()
            assert mock_mm.store.call_args.kwargs["key"] == "new_memory"

    @pytest.mark.asyncio
    async def test_returns_zero_on_empty_messages(self, mock_workflow):
        """Should return 0 when there are no messages with content."""
        mock_workflow.messages = []

        count = await _extract_auto_memories(
            agent_id="agent-1",
            messages=mock_workflow.messages,
            workflow=mock_workflow,
            github_token="fake-token",
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(self, mock_workflow):
        """Should return 0 when LLM returns invalid JSON."""
        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, return_value="not json"):
            mock_stm.get_recent_memories = AsyncMock(return_value=[])

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 0

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self, mock_workflow):
        """Should return 0 when LLM call fails."""
        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, side_effect=Exception("API error")):
            mock_stm.get_recent_memories = AsyncMock(return_value=[])

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 0

    @pytest.mark.asyncio
    async def test_limits_to_five_memories(self, mock_workflow):
        """Should store at most 5 memories even if LLM returns more."""
        llm_response = json.dumps([
            {"key": f"mem_{i}", "value": f"Learning {i}"} for i in range(10)
        ])

        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine.memory_manager") as mock_mm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, return_value=llm_response):
            mock_stm.get_recent_memories = AsyncMock(return_value=[])
            mock_mm.store = AsyncMock(return_value=MagicMock(key="test", scope="agent"))

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 5
            assert mock_mm.store.call_count == 5

    @pytest.mark.asyncio
    async def test_handles_markdown_code_fence(self, mock_workflow):
        """Should parse JSON even when wrapped in markdown code fences."""
        llm_response = '```json\n[{"key": "fenced_mem", "value": "From fenced response"}]\n```'

        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine.memory_manager") as mock_mm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, return_value=llm_response):
            mock_stm.get_recent_memories = AsyncMock(return_value=[])
            mock_mm.store = AsyncMock(return_value=MagicMock(key="fenced_mem", scope="agent"))

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 1

    @pytest.mark.asyncio
    async def test_empty_array_response(self, mock_workflow):
        """Should return 0 when LLM returns empty array."""
        with patch("app.core.agent_engine.memory_stm") as mock_stm, \
             patch("app.core.agent_engine._llm_call_openai_compat", new_callable=AsyncMock, return_value="[]"):
            mock_stm.get_recent_memories = AsyncMock(return_value=[])

            count = await _extract_auto_memories(
                agent_id="agent-1",
                messages=mock_workflow.messages,
                workflow=mock_workflow,
                github_token="fake-token",
            )
            assert count == 0
