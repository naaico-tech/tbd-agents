"""Tests for the agent_engine helper functions."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import (
    _build_system_prompt,
    _compress_caveman_context,
    _parse_todo_list,
)
from app.models.agent import Agent
from app.models.task_execution import TodoItemStatus
from app.models.workflow import Workflow


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
        args_str = json.dumps(
            {"todoList": [{"id": 1, "title": "Task", "status": "not-started"}]}
        )
        result = _parse_todo_list(args_str)
        assert result is not None
        assert len(result.todos) == 1

    def test_invalid_json_string(self):
        result = _parse_todo_list("not-json")
        assert result is None

    def test_invalid_status_defaults(self):
        args = {"todoList": [{"id": 1, "title": "Task", "status": "unknown-status"}]}
        result = _parse_todo_list(args)
        assert result is not None
        assert result.todos[0].status == TodoItemStatus.NOT_STARTED

    def test_missing_fields_use_defaults(self):
        result = _parse_todo_list({"todoList": [{"id": 1, "title": "Task"}]})
        assert result is not None
        assert result.todos[0].status == TodoItemStatus.NOT_STARTED

    def test_list_input_ignored(self):
        result = _parse_todo_list([1, 2, 3])
        assert result is None


class TestAutoMemoryPromptInjection:
    """Test that _build_system_prompt injects auto_memory instructions when enabled."""

    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock(spec=Agent)
        agent.system_prompt = "You are a helpful assistant."
        return agent

    @pytest.fixture
    def mock_workflow_auto_memory_on(self):
        wf = MagicMock(spec=Workflow)
        wf.auto_memory = True
        wf.caveman = False
        wf.output_format = "json"
        return wf

    @pytest.fixture
    def mock_workflow_auto_memory_off(self):
        wf = MagicMock(spec=Workflow)
        wf.auto_memory = False
        wf.caveman = False
        wf.output_format = "json"
        return wf

    @pytest.mark.asyncio
    async def test_auto_memory_enabled_injects_policy(
        self, mock_agent, mock_workflow_auto_memory_on
    ):
        """Should include auto_memory_policy when workflow.auto_memory is True."""
        prompt = await _build_system_prompt(mock_agent, [], mock_workflow_auto_memory_on)
        assert "<auto_memory_policy>" in prompt
        assert "store_memory" in prompt
        assert "snake_case" in prompt

    @pytest.mark.asyncio
    async def test_auto_memory_disabled_no_policy(
        self, mock_agent, mock_workflow_auto_memory_off
    ):
        """Should NOT include auto_memory_policy when workflow.auto_memory is False."""
        prompt = await _build_system_prompt(mock_agent, [], mock_workflow_auto_memory_off)
        assert "<auto_memory_policy>" not in prompt

    @pytest.mark.asyncio
    async def test_auto_memory_preserves_execution_policy(
        self, mock_agent, mock_workflow_auto_memory_on
    ):
        """Auto-memory policy should appear alongside the execution policy."""
        prompt = await _build_system_prompt(mock_agent, [], mock_workflow_auto_memory_on)
        assert "<execution_policy>" in prompt
        assert "<auto_memory_policy>" in prompt

    @pytest.mark.asyncio
    async def test_auto_memory_after_execution_policy(
        self, mock_agent, mock_workflow_auto_memory_on
    ):
        """Auto-memory policy should come after execution policy."""
        prompt = await _build_system_prompt(mock_agent, [], mock_workflow_auto_memory_on)
        exec_pos = prompt.index("<execution_policy>")
        auto_pos = prompt.index("<auto_memory_policy>")
        assert auto_pos > exec_pos


class TestCavemanWorkflowMode:
    @pytest.mark.asyncio
    async def test_caveman_policy_added_to_system_prompt(self):
        agent = MagicMock(spec=Agent)
        agent.system_prompt = "You are helpful."
        workflow = MagicMock(spec=Workflow)
        workflow.auto_memory = False
        workflow.caveman = True
        workflow.output_format = "markdown"

        prompt = await _build_system_prompt(agent, [], workflow)

        assert "<caveman_policy>" in prompt
        assert "workflow output obligation (markdown)" in prompt

    def test_caveman_context_compression_preserves_tags_and_code(self):
        context = (
            "<memories>\n"
            "<memory key=\"prefs\" scope=\"agent\">"
            "It is important to make sure you always run `pytest` before push to main."
            "</memory>\n"
            "</memories>"
        )

        compressed = _compress_caveman_context(context)

        assert "<memories>" in compressed
        assert "<memory key=\"prefs\" scope=\"agent\">" in compressed
        assert "`pytest`" in compressed
        assert "run `pytest` before push main" in compressed
        assert len(compressed) < len(context)


class TestPromptBudgeting:
    @pytest.mark.asyncio
    async def test_skill_injection_respects_budget(self):
        agent = MagicMock(spec=Agent)
        agent.system_prompt = "You are helpful."
        workflow = MagicMock(spec=Workflow)
        workflow.auto_memory = False
        workflow.caveman = False
        workflow.output_format = "json"

        long_skill = MagicMock()
        long_skill.name = "big-skill"
        long_skill.instructions = "X" * 8000

        with patch("app.core.agent_engine.Skill.get", new_callable=AsyncMock, return_value=long_skill):
            prompt = await _build_system_prompt(agent, ["skill-1"], workflow)

        assert "<skills>" in prompt
        assert len(prompt) <= 24000
        assert len(prompt) < len(agent.system_prompt) + len(long_skill.instructions) + 500
        assert "..." in prompt
