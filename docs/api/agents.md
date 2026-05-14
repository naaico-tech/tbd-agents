# Agents API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents` | Create agent |
| `GET` | `/api/agents` | List agents |
| `GET` | `/api/agents/{id}` | Get agent |
| `PUT` | `/api/agents/{id}` | Update agent |
| `DELETE` | `/api/agents/{id}` | Delete agent |
| `GET` | `/api/agents/export` | Export all agents |
| `GET` | `/api/agents/{id}/export` | Export one agent |
| `POST` | `/api/agents/import` | Import agents |

---

## Create Agent

```
POST /api/agents
```

```json
{
  "name": "incident-responder",
  "description": "SRE incident investigation agent",
  "system_prompt": "You are an SRE investigating production incidents.",
  "model": "gpt-4.1",
  "mcp_server_ids": ["<MCP_ID>"],
  "mcp_server_tags": ["observability", "ticketing"],
  "custom_tool_ids": ["<TOOL_ID>"],
  "builtin_tools": ["bash", "read", "grep", "web_fetch"],
  "knowledge_source_ids": ["<SOURCE_ID>"],
  "knowledge_tags": ["runbook"],
  "provider_id": null
}
```

**Response:** `201 Created`

---

## Agent Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique agent name |
| `description` | string | Human-readable description |
| `system_prompt` | string | Agent persona and instructions |
| `model` | string | Model identifier |
| `mcp_server_ids` | string[] | Explicit MCP server IDs |
| `mcp_server_tags` | string[] | Tag-based MCP server resolution |
| `custom_tool_ids` | string[] | IDs of Custom Python Tools mounted on this agent |
| `builtin_tools` | string[] | Platform built-in tool names |
| `tool_definitions` | object[] | Additional provider-compatible tool definitions |
| `knowledge_source_ids` | string[] | Explicit knowledge source IDs |
| `knowledge_tags` | string[] | Tag-based knowledge matching |
| `provider_id` | string \| null | BYOK provider ID; `null` for GitHub Copilot SDK |

Resource-specific import/export endpoints mirror the system import/export API. See [Import & Export](import-export.md).

---

## List Agents

```
GET /api/agents
```

**Response:** `200 OK` — Array of agent objects.

---

## Get Agent

```
GET /api/agents/{id}
```

**Response:** `200 OK` — Single agent object.

---

## Update Agent

```
PUT /api/agents/{id}
```

Accepts the same fields as create. Only provided fields are updated.

**Response:** `200 OK`

---

## Delete Agent

```
DELETE /api/agents/{id}
```

**Response:** `204 No Content`
