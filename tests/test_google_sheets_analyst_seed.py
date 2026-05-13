"""Tests for app/seeds/google_sheets_analyst.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.seeds.google_sheets_analyst import (
    _AGENT_NAME,
    _SYSTEM_PROMPT,
    seed_google_sheets_analyst,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_agent(name=_AGENT_NAME):
    a = MagicMock()
    a.name = name
    a.id = "agent-id-123"
    a.insert = AsyncMock()
    return a


def _make_mock_tool(name="google_sheets"):
    t = MagicMock()
    t.name = name
    t.id = "tool-id-456"
    return t


# ---------------------------------------------------------------------------
# Constant checks
# ---------------------------------------------------------------------------


def test_agent_name_defined():
    assert _AGENT_NAME == "Google Sheets Analyst"


def test_system_prompt_contains_key_instructions():
    assert "SHEETID" in _SYSTEM_PROMPT
    assert "TASKREQUIREMENT" in _SYSTEM_PROMPT
    assert "get_metadata" in _SYSTEM_PROMPT
    assert "create_sheet" in _SYSTEM_PROMPT
    assert "write_values" in _SYSTEM_PROMPT
    assert "get_values" in _SYSTEM_PROMPT


def test_system_prompt_mentions_no_modify_existing():
    assert "Never modify existing sheets" in _SYSTEM_PROMPT or "only write to the newly created tab" in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# seed_google_sheets_analyst
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_skips_if_agent_exists():
    """If the agent already exists, seed does nothing."""
    existing_agent = _make_mock_agent()

    import app.models.agent as agent_mod
    import app.models.custom_tool as tool_mod

    tool_find_mock = AsyncMock(return_value=None)
    with patch.object(agent_mod.Agent, "find_one", AsyncMock(return_value=existing_agent)):
        with patch.object(tool_mod.CustomTool, "find_one", tool_find_mock):
            await seed_google_sheets_analyst()
            # Tool was NOT queried because we short-circuit on existing agent
            tool_find_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_skips_if_tool_missing():
    """If google_sheets plugin not loaded yet, seed logs warning and skips."""
    import app.models.agent as agent_mod
    import app.models.custom_tool as tool_mod

    insert_mock = AsyncMock()
    with patch.object(agent_mod.Agent, "find_one", AsyncMock(return_value=None)):
        with patch.object(tool_mod.CustomTool, "find_one", AsyncMock(return_value=None)):
            with patch.object(agent_mod.Agent, "insert", insert_mock):
                await seed_google_sheets_analyst()
                insert_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_creates_agent_with_tool_id():
    """Happy path: creates agent with google_sheets tool ID."""
    tool = _make_mock_tool()

    inserted: list = []
    mock_instance = MagicMock()
    mock_instance.id = "new-agent-id"
    mock_instance.name = _AGENT_NAME
    mock_instance.custom_tool_ids = [str(tool.id)]
    mock_instance.system_prompt = _SYSTEM_PROMPT
    mock_instance.insert = AsyncMock(side_effect=lambda: inserted.append(mock_instance))

    mock_agent_cls = MagicMock()
    mock_agent_cls.find_one = AsyncMock(return_value=None)
    mock_agent_cls.return_value = mock_instance

    mock_tool_cls = MagicMock()
    mock_tool_cls.find_one = AsyncMock(return_value=tool)

    # Patch at models level so lazy imports in seed pick up mocks
    import app.models.agent as agent_mod
    import app.models.custom_tool as tool_mod

    with patch.object(agent_mod, "Agent", mock_agent_cls):
        with patch.object(tool_mod, "CustomTool", mock_tool_cls):
            await seed_google_sheets_analyst()

    assert len(inserted) == 1
    assert mock_agent_cls.call_args.kwargs["name"] == _AGENT_NAME
    assert str(tool.id) in mock_agent_cls.call_args.kwargs["custom_tool_ids"]
    assert mock_agent_cls.call_args.kwargs["system_prompt"] == _SYSTEM_PROMPT
