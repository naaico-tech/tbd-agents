"""Tests for app/core/plugin_loader.py — plugin discovery and MongoDB upsert."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.plugin_loader import _name_to_class

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin_cls(name: str = "test_plugin", is_enabled: bool = True):
    """Return a minimal concrete PluginBase subclass for use in loader tests."""
    import sys
    import types

    from app.core.plugin_base import PluginBase

    _enabled = is_enabled  # close over the value
    fake_module_name = f"app.plugins._{name}"

    class _TestPlugin(PluginBase):
        @property
        def name(self) -> str:
            return name

        @property
        def description(self) -> str:
            return f"Description for {name}"

        @property
        def is_enabled(self) -> bool:
            return _enabled

        def execute(self, query: str) -> dict:
            return {"result": query}

    # Fake the module so get_source_code() module-path check passes
    _TestPlugin.__module__ = fake_module_name
    if fake_module_name not in sys.modules:
        fake_mod = types.ModuleType(fake_module_name)
        setattr(fake_mod, _TestPlugin.__name__, _TestPlugin)
        sys.modules[fake_module_name] = fake_mod

    return _TestPlugin


# ---------------------------------------------------------------------------
# _name_to_class
# ---------------------------------------------------------------------------


def test_name_to_class_conversion():
    """_name_to_class converts snake_case plugin names to PascalCase class names."""
    assert _name_to_class("mysql_read") == "MysqlReadPlugin"
    assert _name_to_class("web_search") == "WebSearchPlugin"
    assert _name_to_class("simple") == "SimplePlugin"


# ---------------------------------------------------------------------------
# load_plugins_from_config — path / YAML parsing edge cases
# ---------------------------------------------------------------------------


async def test_load_plugins_missing_config(tmp_path):
    """Missing config file returns an empty set without raising."""
    from app.core.plugin_loader import load_plugins_from_config

    result = await load_plugins_from_config(
        config_path=str(tmp_path / "nonexistent.yaml"),
        plugins_dir=str(tmp_path),
    )
    assert result == set()


async def test_load_plugins_empty_yaml(tmp_path):
    """YAML with no 'plugins' key returns an empty set."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text("other_key: some_value\n", encoding="utf-8")

    result = await load_plugins_from_config(
        config_path=str(config_file),
        plugins_dir=str(tmp_path),
    )
    assert result == set()


async def test_load_plugins_all_disabled(tmp_path):
    """Plugins with enabled: false attempt to deactivate existing DB tools."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text(
        "plugins:\n"
        "  - name: alpha\n"
        "    enabled: false\n"
        "  - name: beta\n"
        "    enabled: false\n",
        encoding="utf-8",
    )

    with patch("app.core.plugin_loader.CustomTool") as mock_ct:
        # Return None so there is nothing to deactivate
        mock_ct.find_one = AsyncMock(return_value=None)
        result = await load_plugins_from_config(
            config_path=str(config_file),
            plugins_dir=str(tmp_path),
        )

    assert result == set()
    # find_one is now called once per disabled entry to check for an existing tool
    assert mock_ct.find_one.call_count == 2


# ---------------------------------------------------------------------------
# load_plugins_from_config — DB interaction tests
# ---------------------------------------------------------------------------


async def test_load_plugins_creates_new_tool(tmp_path):
    """When no existing document, a new CustomTool is inserted."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text(
        "plugins:\n"
        "  - name: test_plugin\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    plugin_cls = _make_plugin_cls("test_plugin")
    mock_tool_instance = MagicMock()
    mock_tool_instance.insert = AsyncMock()

    with (
        patch("app.core.plugin_loader._load_plugin_class", return_value=plugin_cls),
        patch("app.core.plugin_loader.CustomTool") as mock_ct,
    ):
        mock_ct.find_one = AsyncMock(return_value=None)
        mock_ct.return_value = mock_tool_instance

        result = await load_plugins_from_config(
            config_path=str(config_file),
            plugins_dir=str(tmp_path),
        )

    # Insert was called exactly once
    mock_tool_instance.insert.assert_called_once()
    # Constructor was called with the right name
    init_kwargs = mock_ct.call_args.kwargs
    assert init_kwargs["name"] == "test_plugin"
    assert "description" in init_kwargs
    assert "source_code" in init_kwargs
    # Plugin name is in the returned set
    assert "test_plugin" in result


async def test_load_plugins_updates_existing_tool(tmp_path):
    """When a document already exists, save() is called (not insert)."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text(
        "plugins:\n"
        "  - name: test_plugin\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    plugin_cls = _make_plugin_cls("test_plugin")

    existing = MagicMock()
    existing.save = AsyncMock()
    existing.source_code = "OLD_SOURCE_CODE"  # differs from generated → triggers update
    existing.parameters_schema = None

    with (
        patch("app.core.plugin_loader._load_plugin_class", return_value=plugin_cls),
        patch("app.core.plugin_loader.CustomTool") as mock_ct,
    ):
        mock_ct.find_one = AsyncMock(return_value=existing)

        result = await load_plugins_from_config(
            config_path=str(config_file),
            plugins_dir=str(tmp_path),
        )

    # save() called instead of insert()
    existing.save.assert_called_once()
    # Metadata fields updated
    assert existing.description == "Description for test_plugin"
    assert "test_plugin" in result


async def test_load_plugins_skips_disabled_plugin_object(tmp_path):
    """Plugin with is_enabled=False on the instance deactivates any existing DB tool."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text(
        "plugins:\n"
        "  - name: disabled_plugin\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    disabled_cls = _make_plugin_cls("disabled_plugin", is_enabled=False)

    with (
        patch("app.core.plugin_loader._load_plugin_class", return_value=disabled_cls),
        patch("app.core.plugin_loader.CustomTool") as mock_ct,
    ):
        # Return None so there is nothing to deactivate
        mock_ct.find_one = AsyncMock(return_value=None)

        result = await load_plugins_from_config(
            config_path=str(config_file),
            plugins_dir=str(tmp_path),
        )

    assert result == set()
    # find_one is now called to check for an existing DB tool to deactivate
    mock_ct.find_one.assert_called_once()


async def test_load_plugins_returns_loaded_names(tmp_path):
    """The returned set contains the names of all successfully loaded plugins."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text(
        "plugins:\n"
        "  - name: plugin_one\n"
        "    enabled: true\n"
        "  - name: plugin_two\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    cls_one = _make_plugin_cls("plugin_one")
    cls_two = _make_plugin_cls("plugin_two")

    mock_tool = MagicMock()
    mock_tool.insert = AsyncMock()

    with (
        patch(
            "app.core.plugin_loader._load_plugin_class",
            side_effect=[cls_one, cls_two],
        ),
        patch("app.core.plugin_loader.CustomTool") as mock_ct,
    ):
        mock_ct.find_one = AsyncMock(return_value=None)
        mock_ct.return_value = mock_tool

        result = await load_plugins_from_config(
            config_path=str(config_file),
            plugins_dir=str(tmp_path),
        )

    assert "plugin_one" in result
    assert "plugin_two" in result
    assert len(result) == 2


async def test_load_plugins_bad_plugin_does_not_block_others(tmp_path):
    """An ImportError on one plugin is caught; subsequent plugins still load."""
    from app.core.plugin_loader import load_plugins_from_config

    config_file = tmp_path / "plugins.yaml"
    config_file.write_text(
        "plugins:\n"
        "  - name: bad_plugin\n"
        "    enabled: true\n"
        "  - name: good_plugin\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    good_cls = _make_plugin_cls("good_plugin")
    mock_tool = MagicMock()
    mock_tool.insert = AsyncMock()

    with (
        patch(
            "app.core.plugin_loader._load_plugin_class",
            side_effect=[ImportError("cannot import bad_plugin"), good_cls],
        ),
        patch("app.core.plugin_loader.CustomTool") as mock_ct,
    ):
        mock_ct.find_one = AsyncMock(return_value=None)
        mock_ct.return_value = mock_tool

        # Should NOT raise — bad plugin error is swallowed
        result = await load_plugins_from_config(
            config_path=str(config_file),
            plugins_dir=str(tmp_path),
        )

    assert "good_plugin" in result
    assert "bad_plugin" not in result
