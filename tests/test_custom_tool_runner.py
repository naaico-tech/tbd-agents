"""Unit tests for app.services.custom_tool_runner."""

import json
import sys

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

SIMPLE_SYNC_TOOL = """
def add(a: int, b: int) -> int:
    return a + b
"""

SIMPLE_ASYNC_TOOL = """
import asyncio

async def greet(name: str) -> str:
    await asyncio.sleep(0)
    return f"Hello, {name}!"
"""

DICT_RETURN_TOOL = """
def info(key: str) -> dict:
    return {"key": key, "value": 42}
"""

FAILING_TOOL = """
def boom(x: int) -> int:
    raise RuntimeError("intentional failure")
"""

NO_FUNC_TOOL = """
x = 1 + 1
"""

UNANNOTATED_TOOL = """
def mystery(a, b):
    return str(a) + str(b)
"""

TIMEOUT_TOOL = """
import time

def slow():
    time.sleep(9999)
"""

ENV_TOOL = """
import os

def get_env_var(var_name: str) -> dict:
    return {"value": os.environ.get(var_name, "not-found")}
"""


# ── validate_tool ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_valid_sync():
    from app.services.custom_tool_runner import validate_tool
    result = await validate_tool(SIMPLE_SYNC_TOOL, "add")
    assert result["valid"] is True
    schema = result["inferred_schema"]
    assert schema["type"] == "object"
    assert "a" in schema["properties"]
    assert "b" in schema["properties"]
    assert schema["properties"]["a"]["type"] == "integer"
    assert "required" in schema and set(schema["required"]) == {"a", "b"}


@pytest.mark.asyncio
async def test_validate_valid_async():
    from app.services.custom_tool_runner import validate_tool
    result = await validate_tool(SIMPLE_ASYNC_TOOL, "greet")
    assert result["valid"] is True
    schema = result["inferred_schema"]
    assert "name" in schema["properties"]
    assert schema["properties"]["name"]["type"] == "string"


@pytest.mark.asyncio
async def test_validate_missing_function():
    from app.services.custom_tool_runner import validate_tool
    result = await validate_tool(NO_FUNC_TOOL, "mystery")
    assert result["valid"] is False
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_validate_syntax_error():
    from app.services.custom_tool_runner import validate_tool
    result = await validate_tool("def broken(:\n    pass", "broken")
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_validate_unannotated_params():
    """Unannotated parameters should default to type 'string'."""
    from app.services.custom_tool_runner import validate_tool
    result = await validate_tool(UNANNOTATED_TOOL, "mystery")
    assert result["valid"] is True
    schema = result["inferred_schema"]
    assert schema["properties"]["a"]["type"] == "string"
    assert schema["properties"]["b"]["type"] == "string"


# ── infer_schema ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_infer_schema_types():
    from app.services.custom_tool_runner import infer_schema
    schema = await infer_schema(SIMPLE_SYNC_TOOL, "add")
    assert schema["properties"]["a"]["type"] == "integer"
    assert schema["properties"]["b"]["type"] == "integer"
    assert "required" in schema
    assert set(schema["required"]) == {"a", "b"}


@pytest.mark.asyncio
async def test_infer_schema_missing_function():
    from app.services.custom_tool_runner import infer_schema
    schema = await infer_schema(NO_FUNC_TOOL, "nonexistent")
    # Should return a safe empty schema on failure
    assert schema.get("type") == "object"
    assert schema.get("properties") == {}


# ── run_tool ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_sync_tool():
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(SIMPLE_SYNC_TOOL, "add", {"a": 3, "b": 4})
    parsed = json.loads(result)
    assert parsed == {"result": "7"}


@pytest.mark.asyncio
async def test_run_async_tool():
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(SIMPLE_ASYNC_TOOL, "greet", {"name": "World"})
    parsed = json.loads(result)
    assert parsed == {"result": "Hello, World!"}


@pytest.mark.asyncio
async def test_run_dict_return():
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(DICT_RETURN_TOOL, "info", {"key": "foo"})
    parsed = json.loads(result)
    assert parsed == {"key": "foo", "value": 42}


@pytest.mark.asyncio
async def test_run_failing_tool():
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(FAILING_TOOL, "boom", {"x": 1})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "intentional failure" in parsed["error"]


@pytest.mark.asyncio
async def test_run_missing_function():
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(NO_FUNC_TOOL, "nonexistent", {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not found" in parsed["error"]


@pytest.mark.asyncio
async def test_run_tool_timeout(monkeypatch):
    """Patch timeout to 1 second and verify the timeout path is hit."""
    import app.services.custom_tool_runner as runner_mod
    monkeypatch.setattr(runner_mod, "CUSTOM_TOOL_TIMEOUT_SECONDS", 1)
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(TIMEOUT_TOOL, "slow", {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "timed out" in parsed["error"]


@pytest.mark.asyncio
async def test_run_env_tool():
    from app.services.custom_tool_runner import run_tool
    result = await run_tool(ENV_TOOL, "get_env_var", {"var_name": "API_KEY"}, env={"API_KEY": "secret-value"})
    parsed = json.loads(result)
    assert parsed == {"value": "secret-value"}
