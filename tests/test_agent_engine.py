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
