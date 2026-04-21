# Agents API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents` | Create agent |
| `GET` | `/api/agents` | List agents |
| `GET` | `/api/agents/{id}` | Get agent |
| `PUT` | `/api/agents/{id}` | Update agent |
| `DELETE` | `/api/agents/{id}` | Delete agent |

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
| `provider_id` | string \| null | BYOK provider ID; `null` for GitHub Copilot SDK |

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
