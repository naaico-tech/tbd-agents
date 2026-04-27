"""Plugin loader — discovers and registers PluginBase subclasses from plugins.yaml."""

from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from app.config import settings
from app.core.plugin_base import PluginBase
from app.models.custom_tool import CustomTool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def _name_to_class(name: str) -> str:
    """Convert a snake_case plugin name to the expected PascalCase class name.

    The class name is formed by capitalising each ``_``-separated segment and
    appending ``"Plugin"``.

    Examples::

        >>> _name_to_class("mysql_read")
        'MysqlReadPlugin'
        >>> _name_to_class("web_search")
        'WebSearchPlugin'
        >>> _name_to_class("repo_inspector")
        'RepoInspectorPlugin'

    Args:
        name: Snake-case plugin identifier, e.g. ``"mysql_read"``.

    Returns:
        PascalCase class name string, e.g. ``"MysqlReadPlugin"``.
    """
    return "".join(part.capitalize() for part in name.split("_")) + "Plugin"


# ---------------------------------------------------------------------------
# Module / class loader
# ---------------------------------------------------------------------------


def _load_plugin_class(name: str, plugins_dir: str) -> type[PluginBase] | None:
    """Import the plugin module and return its concrete :class:`PluginBase` subclass.

    The module is expected at ``app.plugins.{name}`` and the class at
    ``_name_to_class(name)`` within that module.  The *plugins_dir* argument is
    used only to validate that the corresponding ``.py`` file exists before
    attempting the import, so a clear warning can be logged when it is absent.

    Args:
        name: Snake-case plugin name, e.g. ``"mysql_read"``.
        plugins_dir: Filesystem path to the plugins directory, used for
            existence checks only.

    Returns:
        The plugin class (a :class:`PluginBase` subclass), or ``None`` if the
        module or class could not be found.
    """
    plugin_file = Path(plugins_dir) / f"{name}.py"
    if not plugin_file.exists():
        logger.warning(
            "Plugin '%s': expected file '%s' not found — skipping.",
            name,
            plugin_file,
        )
        return None

    module_path = f"app.plugins.{name}"
    class_name = _name_to_class(name)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        logger.warning(
            "Plugin '%s': could not import module '%s': %s — skipping.",
            name,
            module_path,
            exc,
        )
        return None

    cls = getattr(module, class_name, None)
    if cls is None:
        logger.warning(
            "Plugin '%s': class '%s' not found in module '%s' — skipping.",
            name,
            class_name,
            module_path,
        )
        return None

    if not (isinstance(cls, type) and issubclass(cls, PluginBase)):
        logger.warning(
            "Plugin '%s': '%s.%s' is not a PluginBase subclass — skipping.",
            name,
            module_path,
            class_name,
        )
        return None

    return cls


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def load_plugins_from_config(
    config_path: str | None = None,
    plugins_dir: str | None = None,
) -> set[str]:
    """Discover, instantiate, and upsert enabled plugins from *plugins.yaml*.

    Reads the YAML file at *config_path* (defaults to
    :attr:`~app.config.Settings.plugins_config`) and, for every entry with
    ``enabled: true``, imports the corresponding :class:`PluginBase` subclass,
    generates its source code and parameter schema, then upserts a
    :class:`~app.models.custom_tool.CustomTool` document in MongoDB.

    Metadata fields (``description``, ``tags``, ``env_config``) are always kept
    in sync.  When the stored source code and schema are identical to the plugin's
    current output the ``source_code`` / ``parameters_schema`` fields are left
    unchanged (no-op update), avoiding unnecessary writes.

    A single failing plugin does **not** abort the rest; errors are logged and
    the plugin name is excluded from the returned set.

    Args:
        config_path: Path to ``plugins.yaml``.  Falls back to
            :attr:`~app.config.Settings.plugins_config` when ``None``.
        plugins_dir: Filesystem directory that contains plugin modules.  Falls
            back to :attr:`~app.config.Settings.plugins_dir` when ``None``.

    Returns:
        A :class:`set` of snake-case plugin names that were successfully loaded
        and upserted.
    """
    # 1. Resolve paths from settings when not provided explicitly
    resolved_config = config_path or settings.plugins_config
    resolved_plugins_dir = plugins_dir or settings.plugins_dir

    # 2. Read and parse the YAML configuration file
    config_file = Path(resolved_config)
    if not config_file.exists():
        logger.info(
            "Plugin config '%s' not found — no plugins loaded.",
            resolved_config,
        )
        return set()

    try:
        raw = config_file.read_text("utf-8")
        config_data: dict = yaml.safe_load(raw) or {}
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to parse plugin config '%s': %s", resolved_config, exc)
        return set()

    plugin_entries: list[dict] = config_data.get("plugins", [])
    if not plugin_entries:
        logger.info("No plugins defined in '%s'.", resolved_config)
        return set()

    loaded: set[str] = set()

    # 3. Process each enabled plugin entry
    for entry in plugin_entries:
        if not isinstance(entry, dict):
            logger.warning("Invalid plugin entry (not a dict): %r — skipping.", entry)
            continue

        name: str | None = entry.get("name")
        enabled: bool = entry.get("enabled", False)

        if not name:
            logger.warning("Plugin entry missing 'name' field — skipping: %r", entry)
            continue

        if not enabled:
            logger.debug("Plugin '%s' is disabled in config — skipping.", name)
            continue

        try:
            # a. Load the plugin class
            plugin_cls = _load_plugin_class(name, resolved_plugins_dir)
            if plugin_cls is None:
                continue

            # b. Instantiate
            plugin: PluginBase = plugin_cls()

            # c. Respect the plugin's own is_enabled flag
            if not plugin.is_enabled:
                logger.debug(
                    "Plugin '%s': is_enabled=False on instance — skipping.", name
                )
                continue

            # d. Generate source code
            source_code: str = plugin.get_source_code()

            # e. Get parameter schema
            schema: dict = plugin.get_parameters_schema()

            # f. Upsert to MongoDB
            existing = await CustomTool.find_one({"name": plugin.name})

            if existing:
                # Always sync metadata in case it changed
                existing.description = plugin.description
                existing.tags = plugin.tags
                existing.env_config = plugin.env_config
                existing.is_plugin = True
                existing.updated_at = datetime.now(UTC)

                # Only update source / schema when they have changed
                if existing.source_code != source_code or not existing.parameters_schema:
                    existing.source_code = source_code
                    existing.parameters_schema = schema
                    logger.info(
                        "Plugin '%s': source/schema updated in MongoDB.", plugin.name
                    )
                else:
                    logger.debug(
                        "Plugin '%s': source unchanged — metadata-only sync.", plugin.name
                    )

                await existing.save()
            else:
                new_tool = CustomTool(
                    name=plugin.name,
                    description=plugin.description,
                    source_code=source_code,
                    parameters_schema=schema,
                    env_config=plugin.env_config,
                    tags=plugin.tags,
                    is_enabled=True,
                    is_plugin=True,
                )
                await new_tool.insert()
                logger.info("Plugin '%s': registered as new CustomTool.", plugin.name)

            loaded.add(name)

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Plugin '%s': unexpected error during loading — skipping. %s: %s",
                name,
                type(exc).__name__,
                exc,
                exc_info=True,
            )

    # 4. Summary
    logger.info(
        "Plugin loader: %d plugin(s) successfully loaded from '%s'.",
        len(loaded),
        resolved_config,
    )
    return loaded
