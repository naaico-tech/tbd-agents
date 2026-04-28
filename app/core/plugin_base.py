"""Abstract base class for tbd-agents custom tool plugins.

Developers extend :class:`PluginBase` to ship self-contained tool plugins
that integrate seamlessly with the custom_tool_runner subprocess execution
engine and the project's tool registry.

Usage example::

    from app.core.plugin_base import PluginBase

    class GreetPlugin(PluginBase):
        @property
        def name(self) -> str:
            return "greet"

        @property
        def description(self) -> str:
            return "Returns a personalised greeting."

        @property
        def tags(self) -> list[str]:
            return ["demo", "text"]

        def execute(self, name: str, formal: bool = False) -> str:
            prefix = "Good day" if formal else "Hello"
            return f"{prefix}, {name}!"
"""

from __future__ import annotations

import inspect
import keyword
import textwrap
from abc import ABC, abstractmethod
from typing import Any

# ---------------------------------------------------------------------------
# Type-mapping helpers
# ---------------------------------------------------------------------------

#: Maps Python built-in type names to their JSON Schema equivalents.
#: Used by :meth:`PluginBase.get_parameters_schema` and mirrors the mapping
#: used in ``app/services/custom_tool_runner.py``.
_PY_TYPE_TO_JSON: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "None": "null",
}


def _annotation_to_json_type(annotation: Any) -> str:
    """Convert a single Python type annotation to a JSON Schema type string.

    Falls back to ``"string"`` for unknown or un-annotated parameters so that
    the schema remains valid even when type hints are absent.

    Args:
        annotation: The annotation object from ``inspect.Parameter.annotation``,
            or ``inspect.Parameter.empty`` when no annotation is present.

    Returns:
        A JSON Schema type string such as ``"string"``, ``"integer"``, etc.
    """
    if annotation is inspect.Parameter.empty or annotation is None:
        return "string"
    name = getattr(annotation, "__name__", str(annotation))
    return _PY_TYPE_TO_JSON.get(name, "string")


# ---------------------------------------------------------------------------
# PluginBase
# ---------------------------------------------------------------------------


class PluginBase(ABC):
    """Abstract base class that every tbd-agents plugin must extend.

    A *plugin* is a self-contained Python class that exposes a single tool
    function (``execute``) to the agent runtime.  The class carries its own
    metadata (name, description, tags) and optional environment-variable
    configuration, and can auto-generate both its JSON Schema and a standalone
    source-code string suitable for the ``custom_tool_runner`` subprocess
    execution engine.

    Subclassing contract
    --------------------
    Concrete subclasses **must** implement:

    * :attr:`name` – unique, slug-style identifier (e.g. ``"web_search"``).
    * :attr:`description` – human-readable explanation shown to the LLM.
    * :meth:`execute` – the actual tool logic.  Replace ``**kwargs`` with
      explicit, typed keyword arguments; the abstract signature uses ``**kwargs``
      only as a lowest-common-denominator interface.

    Optionally override:

    * :attr:`tags` – categorisation labels (default ``[]``).
    * :attr:`env_config` – mapping of env-var names to ``{{token:X}}``
      references or plain default values (default ``{}``).
    * :attr:`is_enabled` – set to ``False`` to soft-disable the plugin
      without removing it (default ``True``).
    """

    # ------------------------------------------------------------------
    # Abstract properties — must be overridden
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique, slug-style tool name used for invocation.

        Must be a valid Python identifier and should be unique across all
        registered plugins.  Examples: ``"web_search"``, ``"send_email"``.

        Returns:
            The tool's unique name string.
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does.

        This text is surfaced to the LLM in the tool manifest, so it should
        be concise but precise enough to guide correct invocation.

        Returns:
            A plain-text description of the tool's purpose.
        """

    # ------------------------------------------------------------------
    # Optional properties — safe defaults provided
    # ------------------------------------------------------------------

    @property
    def tags(self) -> list[str]:
        """Categorisation labels for filtering and discovery.

        Override to attach one or more tags (e.g. ``["search", "web"]``).

        Returns:
            A list of tag strings; defaults to an empty list.
        """
        return []

    @property
    def env_config(self) -> dict[str, str]:
        """Environment-variable configuration for the plugin.

        Maps environment variable names to ``{{token:X}}`` references (resolved
        at runtime by the token manager) or plain string default values.

        Example::

            {
                "OPENAI_API_KEY": "{{token:openai_key}}",
                "TIMEOUT_SECONDS": "30",
            }

        Returns:
            A dict mapping env-var names to their template/default values;
            defaults to an empty dict.
        """
        return {}

    @property
    def is_enabled(self) -> bool:
        """Whether this plugin is active and should be registered.

        Set to ``False`` on a subclass to soft-disable the plugin without
        removing its code.

        Returns:
            ``True`` if the plugin is active; defaults to ``True``.
        """
        return True

    # ------------------------------------------------------------------
    # Abstract method — must be overridden
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with the provided keyword arguments.

        **Important:** Concrete subclasses should replace the ``**kwargs``
        signature with explicit, typed keyword parameters.  The abstract
        ``**kwargs`` signature exists only as the lowest-common-denominator
        interface; the concrete signature is what drives JSON Schema inference
        in :meth:`get_parameters_schema`.

        Example concrete signature::

            def execute(self, query: str, max_results: int = 10) -> list[dict]:
                ...

        Args:
            **kwargs: Tool-specific keyword arguments.  Replace with explicit
                parameters in your subclass.

        Returns:
            Any JSON-serialisable value.  Dicts and lists are forwarded
            verbatim; other types are wrapped as ``{"result": str(value)}``.
        """

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def get_parameters_schema(self) -> dict:
        """Auto-infer a JSON Schema object from the concrete ``execute`` signature.

        Uses :mod:`inspect` to read the parameter names, type annotations, and
        default values of the *concrete* ``execute`` method (i.e. the one
        defined on the subclass, not the abstract one here).  ``self`` is
        excluded from the schema.

        Type mapping follows :data:`_PY_TYPE_TO_JSON`; unannotated parameters
        fall back to ``"string"``.  Parameters that lack a default value are
        listed in the ``"required"`` array.

        Returns:
            A JSON Schema dict of the form::

                {
                    "type": "object",
                    "properties": {
                        "param_name": {"type": "string"},
                        ...
                    },
                    "required": ["param_name", ...]
                }

            The ``"required"`` key is omitted when all parameters have defaults.
        """
        sig = inspect.signature(type(self).execute)
        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            # Skip **kwargs / *args — they have no fixed schema representation
            if param.kind in (
                inspect.Parameter.VAR_KEYWORD,
                inspect.Parameter.VAR_POSITIONAL,
            ):
                continue

            json_type = _annotation_to_json_type(param.annotation)
            properties[param_name] = {"type": json_type}

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def get_source_code(self) -> str:
        """Generate a standalone Python source-code string for subprocess execution.

        The returned string is suitable for use with ``custom_tool_runner.run_tool``.
        It imports the concrete plugin class from its module, instantiates it,
        and binds its ``execute`` method to a module-level name matching
        :attr:`name` so the runner can invoke it by name.

        The generated code looks like::

            import sys as _sys, os as _os
            _sys.path.insert(0, _os.environ.get('TBD_PROJECT_ROOT', '.'))
            from app.plugins.my_plugin import MyPlugin
            _plugin_instance = MyPlugin()
            my_tool = _plugin_instance.execute

        Returns:
            A Python source-code string ready to be passed to
            ``custom_tool_runner.run_tool`` or stored in the database.

        Raises:
            ValueError: If the plugin's module path cannot be resolved to an
                ``app.plugins.*`` sub-module (e.g. the class is defined inline).
        """
        cls = type(self)
        module_path: str = cls.__module__  # e.g. "app.plugins.my_plugin"
        class_name: str = cls.__name__

        if not module_path.startswith("app.plugins."):
            raise ValueError(
                "Plugin class must be defined in an 'app.plugins.*' module; "
                f"got {module_path!r}."
            )

        # Derive the stem: "app.plugins.my_plugin" → "my_plugin"
        parts = module_path.split(".")
        module_stem = parts[-1]

        tool_name = self.name
        if not tool_name.isidentifier() or keyword.iskeyword(tool_name):
            raise ValueError(
                f"Plugin name {tool_name!r} is not a valid Python identifier or is a "
                "reserved keyword. Plugin names must be valid Python identifiers."
            )

        source = textwrap.dedent(f"""\
            import sys as _sys, os as _os
            _sys.path.insert(0, _os.environ.get('TBD_PROJECT_ROOT', '.'))
            from app.plugins.{module_stem} import {class_name}
            _plugin_instance = {class_name}()
            {tool_name} = _plugin_instance.execute
        """)
        return source
