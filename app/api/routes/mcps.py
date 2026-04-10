from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.mcp_server import McpServer, TransportType
from app.schemas.mcp import McpServerCreate, McpServerResponse, McpTestResponse
from app.services.mcp_manager import mcp_manager

router = APIRouter(prefix="/api/mcps", tags=["mcp servers"])


def _to_response(server: McpServer) -> McpServerResponse:
    return McpServerResponse(
        id=str(server.id),
        name=server.name,
        transport_type=server.transport_type,
        connection_config=server.connection_config,
        status=server.status,
        last_error=server.last_error,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.post("", response_model=McpServerResponse, status_code=201)
async def register_mcp_server(body: McpServerCreate, _user=Depends(get_current_user)):
    if body.transport_type not in (TransportType.STDIO, TransportType.SSE):
        raise HTTPException(status_code=400, detail="transport_type must be 'stdio' or 'sse'")
    server = McpServer(
        name=body.name,
        transport_type=TransportType(body.transport_type),
        connection_config=body.connection_config,
    )
    await server.insert()
    return _to_response(server)


@router.get("", response_model=list[McpServerResponse])
async def list_mcp_servers(_user=Depends(get_current_user)):
    servers = await McpServer.find_all().to_list()
    return [_to_response(s) for s in servers]


@router.get("/{server_id}", response_model=McpServerResponse)
async def get_mcp_server(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(PydanticObjectId(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return _to_response(server)


@router.post("/{server_id}/test", response_model=McpTestResponse)
async def test_mcp_server(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(PydanticObjectId(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    result = await mcp_manager.test_connection(server)
    return McpTestResponse(**result)


@router.get("/{server_id}/tools")
async def list_mcp_tools(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(PydanticObjectId(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        tools = await mcp_manager.list_tools(server)
        return {"tools": tools}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to list tools: {e}")


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(server_id: str, _user=Depends(get_current_user)):
    server = await McpServer.get(PydanticObjectId(server_id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await server.delete()
