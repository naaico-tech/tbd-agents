# MCP Servers API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/mcps` | Register MCP server |
| `GET` | `/api/mcps` | List MCP servers |
| `GET` | `/api/mcps/{server_id}` | Get MCP server |
| `PUT` | `/api/mcps/{server_id}` | Update server metadata/config |
| `POST` | `/api/mcps/{server_id}/test` | Test connection |
| `GET` | `/api/mcps/{server_id}/tools` | Discover/list tools |
| `PUT` | `/api/mcps/{server_id}/tools` | Update allowed tools |
| `DELETE` | `/api/mcps/{server_id}` | Delete server |

## Register

```json
{
  "name": "jira",
  "transport_type": "stdio",
  "connection_config": {
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-server-atlassian"],
    "env": {
      "ATLASSIAN_API_TOKEN": "...",
      "ATLASSIAN_EMAIL": "...",
      "ATLASSIAN_URL": "..."
    }
  },
  "tags": ["ticketing"],
  "allowed_tools": []
}
```

Use `PUT /api/mcps/{server_id}/tools` to restrict the server to a selected set of tool names after discovery.
