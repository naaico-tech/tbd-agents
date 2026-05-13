"""Tests for app/core/plugin_base.py — PluginBase abstract base class."""

from __future__ import annotations

import pytest

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Helpers — inline concrete plugins
# ---------------------------------------------------------------------------


def _make_minimal_plugin():
    """Return a minimal concrete PluginBase subclass (name, description, execute only)."""

    class MinimalPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "minimal"

        @property
        def description(self) -> str:
            return "A minimal test plugin."

        def execute(self, **kwargs):
            return {"ok": True}

    return MinimalPlugin


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cannot_instantiate_abstract():
    """PluginBase cannot be instantiated directly — it's abstract."""
    with pytest.raises(TypeError):
        PluginBase()  # type: ignore[abstract]


def test_minimal_plugin_name_description_execute():
    """A minimal concrete plugin can be instantiated and executed."""
    cls = _make_minimal_plugin()
    plugin = cls()
    assert plugin.name == "minimal"
    assert plugin.description == "A minimal test plugin."
    assert plugin.execute() == {"ok": True}


def test_default_property_values():
    """Default values for tags, env_config, and is_enabled are correct."""
    plugin = _make_minimal_plugin()()
    assert plugin.tags == []
    assert plugin.env_config == {}
    assert plugin.is_enabled is True


def test_get_parameters_schema_required_and_optional():
    """Schema correctly separates required and optional parameters."""

    class SchemaPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "schema_test"

        @property
        def description(self) -> str:
            return "Tests schema inference."

        def execute(self, query: str, max_rows: int = 10) -> dict:
            return {}

    plugin = SchemaPlugin()
    schema = plugin.get_parameters_schema()

    assert schema["properties"] == {
        "query": {"type": "string"},
        "max_rows": {"type": "integer"},
    }
    assert schema["required"] == ["query"]
    assert "max_rows" not in schema["required"]


def test_get_parameters_schema_all_optional():
    """When all parameters have defaults, the 'required' key is absent."""

    class AllOptionalPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "all_optional"

        @property
        def description(self) -> str:
            return "All optional params."

        def execute(self, limit: int = 5, offset: int = 0) -> dict:
            return {}

    plugin = AllOptionalPlugin()
    schema = plugin.get_parameters_schema()
    assert "required" not in schema


def test_get_parameters_schema_no_params():
    """Execute with no params → properties == {} and no 'required' key."""

    class NoParamPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "no_params"

        @property
        def description(self) -> str:
            return "No params."

        def execute(self) -> dict:
            return {}

    plugin = NoParamPlugin()
    schema = plugin.get_parameters_schema()
    assert schema["properties"] == {}
    assert "required" not in schema


def test_get_parameters_schema_unannotated():
    """Unannotated parameters fall back to type 'string'."""

    class UnannotatedPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "unannotated"

        @property
        def description(self) -> str:
            return "Unannotated param."

        def execute(self, value) -> dict:  # no annotation on `value`
            return {}

    plugin = UnannotatedPlugin()
    schema = plugin.get_parameters_schema()
    assert schema["properties"]["value"]["type"] == "string"


def test_get_source_code_contains_class_and_name():
    """get_source_code() output contains the expected structural strings."""
    from app.plugins.mysql_read import MysqlReadPlugin

    plugin = MysqlReadPlugin()
    source = plugin.get_source_code()

    # Class name referenced in the import and instantiation
    assert "MysqlReadPlugin" in source
    # Plugin name bound as a module-level variable
    assert "mysql_read = _plugin_instance.execute" in source
    # TBD_PROJECT_ROOT env-var for path setup
    assert "TBD_PROJECT_ROOT" in source
    # Import from the plugins package
    assert "from app.plugins." in source


def test_mysql_read_plugin_schema():
    """MysqlReadPlugin has correct name and parameter schema."""
    from app.plugins.mysql_read import MysqlReadPlugin

    plugin = MysqlReadPlugin()
    assert plugin.name == "mysql_read"

    schema = plugin.get_parameters_schema()
    # 'query' is required and typed string
    assert "query" in schema["required"]
    assert schema["properties"]["query"]["type"] == "string"
    # 'max_rows' is optional and typed integer
    assert schema["properties"]["max_rows"]["type"] == "integer"
    assert "max_rows" not in schema.get("required", [])


def test_repo_inspector_plugin_schema():
    """RepoInspectorPlugin has correct name and 'operation' as required string."""
    from app.plugins.repo_inspector import RepoInspectorPlugin

    plugin = RepoInspectorPlugin()
    assert plugin.name == "repo_inspector"

    schema = plugin.get_parameters_schema()
    assert "operation" in schema["required"]
    assert schema["properties"]["operation"]["type"] == "string"


def test_get_source_code_raises_for_non_plugin_module():
    """get_source_code() raises ValueError when class is not in app.plugins.*."""
    from app.core.plugin_base import PluginBase

    class OutsiderPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "outsider"

        @property
        def description(self) -> str:
            return "An outsider plugin."

        def execute(self, x: str) -> dict:
            return {}

    plugin = OutsiderPlugin()
    with pytest.raises(ValueError, match="app.plugins"):
        plugin.get_source_code()


def test_get_source_code_raises_for_invalid_name():
    """get_source_code() raises ValueError when plugin name is not a valid identifier."""
    import sys
    import types

    # Create a fake module under app.plugins so the module check passes
    fake_mod = types.ModuleType("app.plugins._test_invalid_name")
    sys.modules["app.plugins._test_invalid_name"] = fake_mod
    try:
        from app.core.plugin_base import PluginBase

        class InvalidNamePlugin(PluginBase):
            @property
            def name(self) -> str:
                return "not-valid!"

            @property
            def description(self) -> str:
                return "Invalid name."

            def execute(self, x: str) -> dict:
                return {}

        # Patch __module__ so the module path check passes
        InvalidNamePlugin.__module__ = "app.plugins._test_invalid_name"
        plugin = InvalidNamePlugin()
        with pytest.raises(ValueError, match="not a valid Python identifier"):
            plugin.get_source_code()
    finally:
        sys.modules.pop("app.plugins._test_invalid_name", None)
