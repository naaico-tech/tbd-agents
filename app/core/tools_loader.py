"""Auto-loading script to sync Custom Tools from the local filesystem to MongoDB."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.models.custom_tool import CustomTool
from app.services import custom_tool_runner

logger = logging.getLogger(__name__)


async def load_tools_from_disk(
    tools_dir: str = "app/tools",
    skip_names: set[str] | None = None,
) -> None:
    """Scan the local tools directory and upsert tools into MongoDB.

    Each ``.py`` file is parsed as a Custom Tool whose name matches the filename.
    A companion ``.json`` file (e.g., `weather.json` for `weather.py`) can provide
    extra configuration, such as tags, description, and token-backed environment variables.

    Args:
        tools_dir: Path to the directory containing raw ``.py`` tool files.
        skip_names: Optional set of tool names to skip (e.g. already loaded as plugins).
    """
    tools_path = Path(tools_dir)
    if not tools_path.exists() or not tools_path.is_dir():
        logger.info("Tools directory '%s' not found. Skipping auto-loading.", tools_dir)
        return

    logger.info("Scanning '%s' for custom tools...", tools_dir)
    loaded_count = 0

    for py_file in tools_path.glob("*.py"):
        if py_file.name.startswith("__"):
            continue

        func_name = py_file.stem
        if skip_names and func_name in skip_names:
            logger.debug("Skipping '%s' — already loaded as a plugin.", func_name)
            continue
        source_code = py_file.read_text("utf-8")

        # Basic default config
        tool_config = {
            "description": f"Auto-loaded from {py_file.name}",
            "tags": ["auto-loaded"],
            "env_config": {},
            "is_enabled": True,
        }

        # Look for companion JSON config
        json_file = py_file.with_suffix(".json")
        if json_file.exists():
            try:
                file_config = json.loads(json_file.read_text("utf-8"))
                if "description" in file_config:
                    tool_config["description"] = file_config["description"]
                if "tags" in file_config:
                    tool_config["tags"] = file_config["tags"]
                if "env_config" in file_config:
                    tool_config["env_config"] = file_config["env_config"]
                if "is_enabled" in file_config:
                    tool_config["is_enabled"] = file_config["is_enabled"]
            except Exception as exc:
                logger.warning("Failed to parse companion config '%s': %s", json_file.name, exc)

        # Check existing tool in DB to avoid unnecessary schema inference on identical code
        existing_tool = await CustomTool.find_one({"name": func_name})

        schema = {}
        code_unchanged = existing_tool and existing_tool.source_code == source_code
        if code_unchanged and existing_tool.parameters_schema:
            schema = existing_tool.parameters_schema
        else:
            validation = await custom_tool_runner.validate_tool(source_code, func_name)
            if not validation.get("valid"):
                logger.error("Failed to load '%s': %s", py_file.name, validation.get("error"))
                continue
            schema = validation.get("inferred_schema") or await custom_tool_runner.infer_schema(
                source_code, func_name
            )

        if existing_tool:
            # Update
            existing_tool.source_code = source_code
            existing_tool.parameters_schema = schema
            existing_tool.description = tool_config["description"]
            existing_tool.tags = tool_config["tags"]
            existing_tool.env_config = tool_config["env_config"]
            existing_tool.is_enabled = tool_config["is_enabled"]
            existing_tool.updated_at = datetime.now(UTC)
            await existing_tool.save()
            logger.info("Updated custom tool: '%s'", func_name)
        else:
            # Create
            new_tool = CustomTool(
                name=func_name,
                source_code=source_code,
                parameters_schema=schema,
                description=tool_config["description"],
                tags=tool_config["tags"],
                env_config=tool_config["env_config"],
                is_enabled=tool_config["is_enabled"],
            )
            await new_tool.insert()
            logger.info("Created custom tool: '%s'", func_name)

        loaded_count += 1

    logger.info("Auto-loaded %d custom tool(s).", loaded_count)
