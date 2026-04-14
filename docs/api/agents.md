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
  "mcp_server_tags": ["observability", "ticketing"]
}
```

**Response:** `201 Created`

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
