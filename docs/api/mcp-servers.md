# MCP Servers API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/mcps` | Register MCP server |
| `GET` | `/api/mcps` | List MCP servers |
| `GET` | `/api/mcps/{id}` | Get MCP server |
| `PUT` | `/api/mcps/{id}` | Update MCP server config |
| `POST` | `/api/mcps/{id}/test` | Test MCP connection |
| `GET` | `/api/mcps/{id}/tools` | List tools from MCP server |
| `PUT` | `/api/mcps/{id}/tools` | Update allowed tool names |
| `DELETE` | `/api/mcps/{id}` | Remove MCP server |

---

## Register MCP Server

```
POST /api/mcps
```

=== "stdio"

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
      "tags": ["ticketing"]
    }
    ```

=== "sse"

    ```json
    {
      "name": "custom-tools",
      "transport_type": "sse",
      "connection_config": {
        "url": "http://my-tool-server:3000/sse",
        "headers": {"Authorization": "Bearer secret"}
      },
      "tags": ["internal"]
    }
    ```

**Response:** `201 Created`

---

## List MCP Servers

```
GET /api/mcps
```

**Response:** `200 OK` — Array of MCP server objects.

---

## Get MCP Server

```
GET /api/mcps/{id}
```

**Response:** `200 OK`

---

## Update MCP Server

```
PUT /api/mcps/{id}
```

Updates server metadata, transport settings, connection config, tags, or enabled state.

---

## Test Connection

```
POST /api/mcps/{id}/test
```

Tests whether the MCP server can be reached and responds correctly.

**Response:** `200 OK` — `{status: "connected"}` or error details.

---

## List Tools

```
GET /api/mcps/{id}/tools
```

Returns the list of tools exposed by the MCP server.

**Response:** `200 OK` — Array of tool definitions.

---

## Update Allowed Tools

```
PUT /api/mcps/{id}/tools
```

Use this endpoint to restrict the MCP tools exposed to agents by setting the server's allowed tool names.

---

## Remove MCP Server

```
DELETE /api/mcps/{id}
```

**Response:** `204 No Content`
