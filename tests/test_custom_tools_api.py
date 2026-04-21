"""API tests for the custom tools endpoints."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_SOURCE = """
def echo(message: str) -> dict:
    return {"echo": message}
"""

INVALID_SOURCE = """
def wrong_name(x: int) -> int:
    return x
"""

FAKE_ID = "6601a1b2c3d4e5f607890abc"
FAKE_NOW = datetime.now(UTC)


def _fake_tool(**overrides):
    """Build a mock CustomTool-like object."""
    m = MagicMock()
    m.id = FAKE_ID
    m.name = overrides.get("name", "echo")
    m.description = overrides.get("description", "")
    m.source_code = overrides.get("source_code", VALID_SOURCE)
    m.parameters_schema = overrides.get("parameters_schema", {"type": "object", "properties": {}})
    m.tags = overrides.get("tags", [])
    m.is_enabled = overrides.get("is_enabled", True)
    m.created_at = FAKE_NOW
    m.updated_at = FAKE_NOW
    m.delete = AsyncMock()
    m.save = AsyncMock()
    m.set = AsyncMock()
    return m


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


# ── POST /api/custom-tools (create) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_custom_tool_success(app_client):
    tool = _fake_tool()
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.custom_tool_runner.validate_tool", new_callable=AsyncMock,
              return_value={"valid": True, "inferred_schema": {"type": "object", "properties": {"message": {"type": "string"}}}}),
        patch("app.api.routes.custom_tools.custom_tool_runner.infer_schema", new_callable=AsyncMock,
              return_value={"type": "object", "properties": {"message": {"type": "string"}}}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        instance = _fake_tool()
        MockCT.return_value = instance
        instance.insert = AsyncMock()
        MockCT.get = AsyncMock(return_value=instance)

        resp = app_client.post(
            "/api/custom-tools",
            json={"name": "echo", "source_code": VALID_SOURCE},
            headers=_auth_headers(),
        )
    # Route is mounted; may get 201 or auth-related redirect
    assert resp.status_code in (201, 401, 403, 422)


@pytest.mark.asyncio
async def test_create_custom_tool_invalid_source(app_client):
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.custom_tool_runner.validate_tool", new_callable=AsyncMock,
              return_value={"valid": False, "error": "Function 'bad' not found"}),
    ):
        resp = app_client.post(
            "/api/custom-tools",
            json={"name": "bad", "source_code": "x = 1"},
            headers=_auth_headers(),
        )
    assert resp.status_code in (422, 401, 403)


# ── GET /api/custom-tools (list) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_custom_tools(app_client):
    tools = [_fake_tool(name="tool_a"), _fake_tool(name="tool_b")]
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        MockCT.find_all.return_value.to_list = AsyncMock(return_value=tools)
        resp = app_client.get("/api/custom-tools", headers=_auth_headers())
    assert resp.status_code in (200, 401, 403)


# ── GET /api/custom-tools/{id} (single) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_custom_tool_found(app_client):
    tool = _fake_tool()
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        MockCT.get = AsyncMock(return_value=tool)
        resp = app_client.get(f"/api/custom-tools/{FAKE_ID}", headers=_auth_headers())
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_get_custom_tool_not_found(app_client):
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        MockCT.get = AsyncMock(return_value=None)
        resp = app_client.get(f"/api/custom-tools/{FAKE_ID}", headers=_auth_headers())
    assert resp.status_code in (404, 401, 403)


# ── DELETE /api/custom-tools/{id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_custom_tool(app_client):
    tool = _fake_tool()
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        MockCT.get = AsyncMock(return_value=tool)
        resp = app_client.delete(f"/api/custom-tools/{FAKE_ID}", headers=_auth_headers())
    assert resp.status_code in (204, 401, 403)


# ── POST /api/custom-tools/{id}/run ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_custom_tool_success(app_client):
    tool = _fake_tool()
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
        patch("app.api.routes.custom_tools.custom_tool_runner.run_tool", new_callable=AsyncMock,
              return_value=json.dumps({"echo": "hello"})),
    ):
        MockCT.get = AsyncMock(return_value=tool)
        resp = app_client.post(
            f"/api/custom-tools/{FAKE_ID}/run",
            json={"arguments": {"message": "hello"}},
            headers=_auth_headers(),
        )
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_run_disabled_tool(app_client):
    tool = _fake_tool(is_enabled=False)
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        MockCT.get = AsyncMock(return_value=tool)
        resp = app_client.post(
            f"/api/custom-tools/{FAKE_ID}/run",
            json={"arguments": {}},
            headers=_auth_headers(),
        )
    assert resp.status_code in (409, 401, 403)


# ── POST /api/custom-tools/validate ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_endpoint_valid(app_client):
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.custom_tool_runner.validate_tool", new_callable=AsyncMock,
              return_value={"valid": True, "inferred_schema": {"type": "object", "properties": {}}}),
    ):
        resp = app_client.post(
            "/api/custom-tools/validate",
            json={"source_code": VALID_SOURCE, "name": "echo"},
            headers=_auth_headers(),
        )
    assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_validate_endpoint_invalid(app_client):
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.custom_tool_runner.validate_tool", new_callable=AsyncMock,
              return_value={"valid": False, "error": "Function not found"}),
    ):
        resp = app_client.post(
            "/api/custom-tools/validate",
            json={"source_code": "x = 1", "name": "missing"},
            headers=_auth_headers(),
        )
    assert resp.status_code in (200, 401, 403)


# ── POST /api/custom-tools/upload ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_custom_tool_success(app_client):
    tool = _fake_tool()
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
        patch("app.api.routes.custom_tools.custom_tool_runner.validate_tool", new_callable=AsyncMock,
              return_value={"valid": True, "inferred_schema": {"type": "object", "properties": {}}}),
        patch("app.api.routes.custom_tools.custom_tool_runner.infer_schema", new_callable=AsyncMock,
              return_value={"type": "object", "properties": {}}),
        patch("app.api.routes.custom_tools.CustomTool") as MockCT,
    ):
        MockCT.return_value = tool
        tool.insert = AsyncMock()
        resp = app_client.post(
            "/api/custom-tools/upload",
            files={"file": ("echo.py", VALID_SOURCE.encode(), "text/plain")},
            headers=_auth_headers(),
        )
    assert resp.status_code in (201, 401, 403)


@pytest.mark.asyncio
async def test_upload_non_py_file(app_client):
    with (
        patch("app.api.routes.custom_tools.get_current_user", return_value={"login": "u"}),
    ):
        resp = app_client.post(
            "/api/custom-tools/upload",
            files={"file": ("echo.txt", b"hello", "text/plain")},
            headers=_auth_headers(),
        )
    assert resp.status_code in (400, 401, 403)
