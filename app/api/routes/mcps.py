from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.mcp_server import McpServer, McpServerStatus, TransportType
from app.schemas.mcp import McpServerCreate, McpServerResponse, McpServerUpdate, McpTestResponse
from app.services.mcp_manager import mcp_manager

router = APIRouter(prefix="/api/mcps", tags=["mcp servers"])


def _to_response(server: McpServer) -> McpServerResponse:
    return McpServerResponse(
        id=str(server.id),
        name=server.name,
        transport_type=server.transport_type,
        connection_config=server.connection_config,
        allowed_tools=server.allowed_tools,
        tags=server.tags,
        status=server.status,
        last_error=server.last_error,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.post("", response_model=McpServerResponse, status_code=201)
async def register_mcp_server(body: McpServerCreate, _user=Depends(get_current_user)):
    if body.transport_type not in (TransportType.STDIO, TransportType.SSE, TransportType.HTTP):
        raise HTTPException(status_code=400, detail="transport_type must be 'stdio', 'sse', or 'http'")
    server = McpServer(
        name=body.name,
        transport_type=TransportType(body.transport_type),
        connection_config=body.connection_config,
        allowed_tools=body.allowed_tools,
        tags=body.tags,
    )
    await server.insert()
    return _to_response(server)


@router.get("", response_model=list[McpServerResponse])
async def list_mcp_servers(_user=Depends(get_current_user)):
    servers = await McpServer.find_all().to_list()
    return [_to_response(s) for s in servers]


@router.get("/{server_id}", response_model=McpServerResponse)
async def get_mcp_server(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(parse_doc_id(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return _to_response(server)


@router.post("/{server_id}/test", response_model=McpTestResponse)
async def test_mcp_server(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(parse_doc_id(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    result = await mcp_manager.test_connection(server)
    return McpTestResponse(**result)


@router.get("/{server_id}/tools")
async def list_mcp_tools(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(parse_doc_id(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        tools = await mcp_manager.list_tools(server)
        return {"tools": tools}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to list tools: {e}")


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(parse_doc_id(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await server.delete()


@router.put("/{server_id}", response_model=McpServerResponse)
async def update_mcp_server(
    server_id: str, body: McpServerUpdate, _user=Depends(get_current_user)
):
    server = await McpServer.get(parse_doc_id(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if body.name is not None:
        server.name = body.name
    if body.transport_type is not None:
        if body.transport_type not in (TransportType.STDIO, TransportType.SSE, TransportType.HTTP):
            raise HTTPException(status_code=400, detail="transport_type must be 'stdio', 'sse', or 'http'")
        server.transport_type = TransportType(body.transport_type)
    if body.connection_config is not None:
        server.connection_config = body.connection_config
    if body.allowed_tools is not None:
        server.allowed_tools = body.allowed_tools
    if body.tags is not None:
        server.tags = body.tags
    from datetime import UTC, datetime
    server.updated_at = datetime.now(UTC)
    server.status = McpServerStatus.REGISTERED
    await server.save()
    return _to_response(server)


@router.put("/{server_id}/tools")
async def update_mcp_tools(
    server_id: str, body: dict, _user=Depends(get_current_user)
):
    """Save the list of allowed tool names for an MCP server."""
    server = await McpServer.get(parse_doc_id(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    tools = body.get("allowed_tools", [])
    if not isinstance(tools, list):
        raise HTTPException(status_code=400, detail="allowed_tools must be a list of strings")
    server.allowed_tools = [str(t) for t in tools]
    from datetime import UTC, datetime
    server.updated_at = datetime.now(UTC)
    await server.save()
    return {"allowed_tools": server.allowed_tools}
