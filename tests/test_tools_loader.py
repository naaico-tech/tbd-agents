"""Unit tests for the custom tools auto-loader script."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.custom_tool import CustomTool


@pytest.fixture()
def mock_tools_dir(tmp_path):
    """Create a temporary directory with some tool scripts."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # Tool 1: no json configuration
    py_tool1 = tools_dir / "simple_tool.py"
    py_tool1.write_text("def simple_tool(): pass\n")

    # Tool 2: with json configuration
    py_tool2 = tools_dir / "complex_tool.py"
    py_tool2.write_text("def complex_tool(a: int): pass\n")

    json_tool2 = tools_dir / "complex_tool.json"
    json_tool2.write_text(json.dumps({
        "description": "A complex tool",
        "tags": ["advanced"],
        "env_config": {"API_KEY": "{{token:my_token}}"},
        "is_enabled": False
    }))

    # Tool 3: ignored (prefix __)
    py_ignored = tools_dir / "__init__.py"
    py_ignored.write_text("pass\n")

    return str(tools_dir)


@pytest.mark.asyncio
async def test_load_tools_from_disk_creates_new(mock_tools_dir):
    from app.core.tools_loader import load_tools_from_disk
    from unittest.mock import MagicMock

    mock_doc = MagicMock()
    mock_doc.insert = AsyncMock()

    with (
        patch("app.core.tools_loader.CustomTool", return_value=mock_doc) as mock_cls,
        patch("app.core.tools_loader.custom_tool_runner.validate_tool", new_callable=AsyncMock) as mock_validate,
        patch("app.core.tools_loader.custom_tool_runner.infer_schema", new_callable=AsyncMock) as mock_infer,
    ):
        mock_cls.find_one = AsyncMock(return_value=None)
        mock_validate.return_value = {"valid": True, "inferred_schema": None}
        mock_infer.return_value = {"type": "object"}

        await load_tools_from_disk(mock_tools_dir)

        assert mock_doc.insert.call_count == 2
        calls = mock_cls.call_args_list
        tool_names = {call[1]["name"] for call in calls}
        assert "simple_tool" in tool_names
        assert "complex_tool" in tool_names


@pytest.mark.asyncio
async def test_load_tools_from_disk_proper_objects(mock_tools_dir):
    from app.core.tools_loader import load_tools_from_disk
    from unittest.mock import MagicMock

    created_tools = []
    def mock_doc_constructor(**kwargs):
        doc = MagicMock(**kwargs)
        doc.insert = AsyncMock()
        created_tools.append(doc)
        return doc

    with (
        patch("app.core.tools_loader.CustomTool", side_effect=mock_doc_constructor) as mock_cls,
        patch("app.core.tools_loader.custom_tool_runner.validate_tool", new_callable=AsyncMock, return_value={"valid": True, "inferred_schema": {"type": "object"}}),
    ):
        mock_cls.find_one = AsyncMock(return_value=None)
        await load_tools_from_disk(mock_tools_dir)

    assert len(created_tools) == 2
    
    complex_t = next(t for t in created_tools if "advanced" in t.tags)
    simple_t = next(t for t in created_tools if "auto-loaded" in t.tags)
    
    assert complex_t.description == "A complex tool"
    assert complex_t.tags == ["advanced"]
    assert complex_t.env_config == {"API_KEY": "{{token:my_token}}"}
    assert complex_t.is_enabled is False

    assert "Auto-loaded" in simple_t.description
    assert simple_t.tags == ["auto-loaded"]
    assert simple_t.env_config == {}
    assert simple_t.is_enabled is True


@pytest.mark.asyncio
async def test_load_tools_skips_plugin_names(tmp_path):
    """Tools whose names appear in skip_names are never constructed or inserted."""
    from app.core.tools_loader import load_tools_from_disk
    from unittest.mock import MagicMock

    # Minimal tools directory with only the file we want to skip
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "mysql_read.py").write_text("def mysql_read(query: str): pass\n")

    mock_doc = MagicMock()
    mock_doc.insert = AsyncMock()

    with (
        patch("app.core.tools_loader.CustomTool", return_value=mock_doc) as mock_cls,
        patch(
            "app.core.tools_loader.custom_tool_runner.validate_tool",
            new_callable=AsyncMock,
        ) as mock_validate,
    ):
        mock_cls.find_one = AsyncMock(return_value=None)
        mock_validate.return_value = {"valid": True, "inferred_schema": {"type": "object"}}

        await load_tools_from_disk(str(tools_dir), skip_names={"mysql_read"})

    # Neither the constructor nor insert should have been called for mysql_read
    mock_cls.assert_not_called()
    mock_doc.insert.assert_not_called()
