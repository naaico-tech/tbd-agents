# API Reference

All endpoints (except `/health`) require an `Authorization: Bearer <GITHUB_TOKEN>` header.

---

## Health

```
GET /health
```

---

## Agents

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents` | Create agent |
| `GET` | `/api/agents` | List agents |
| `GET` | `/api/agents/{id}` | Get agent |
| `PUT` | `/api/agents/{id}` | Update agent |
| `DELETE` | `/api/agents/{id}` | Delete agent |

---

## Skills

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/skills` | Create skill |
| `GET` | `/api/skills` | List skills |
| `GET` | `/api/skills/{id}` | Get skill |
| `PUT` | `/api/skills/{id}` | Update skill |
| `DELETE` | `/api/skills/{id}` | Delete skill |

---

## MCP Servers

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/mcps` | Register MCP server |
| `GET` | `/api/mcps` | List MCP servers |
| `GET` | `/api/mcps/{id}` | Get MCP server |
| `POST` | `/api/mcps/{id}/test` | Test MCP connection |
| `GET` | `/api/mcps/{id}/tools` | List tools from MCP server |
| `DELETE` | `/api/mcps/{id}` | Remove MCP server |

---

## Knowledge Sources

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/knowledge-sources` | Register knowledge source (`vector_db` or `mongo_db`) |
| `GET` | `/api/knowledge-sources` | List sources (optional `?tags=` filter) |
| `GET` | `/api/knowledge-sources/{id}` | Get source |
| `PUT` | `/api/knowledge-sources/{id}` | Update source |
| `DELETE` | `/api/knowledge-sources/{id}` | Delete source (cascade-deletes items) |
| `POST` | `/api/knowledge-sources/{id}/test` | Test connection |

---

## Knowledge Items

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/knowledge-items` | Create text knowledge item |
| `POST` | `/api/knowledge-items/upload` | Upload file/image (multipart) |
| `GET` | `/api/knowledge-items` | List items (`?source_id=`, `?tags=`, `?content_type=`) |
| `GET` | `/api/knowledge-items/{id}` | Get item metadata |
| `GET` | `/api/knowledge-items/{id}/content` | Download file content |
| `PUT` | `/api/knowledge-items/{id}` | Update item tags/metadata |
| `DELETE` | `/api/knowledge-items/{id}` | Delete item |
| `POST` | `/api/knowledge-items/query` | Query items by tags |

---

## Workflows

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/workflows` | Create workflow |
| `GET` | `/api/workflows` | List your workflows |
| `GET` | `/api/workflows/{id}` | Get workflow state + logs + messages |
| `PUT` | `/api/workflows/{id}` | Update workflow |
| `DELETE` | `/api/workflows/{id}` | Delete workflow |
| `POST` | `/api/workflows/{id}/prompt` | Send prompt (returns 201, runs via worker) |
| `POST` | `/api/workflows/{id}/halt` | Halt running workflow |
| `GET` | `/api/workflows/{id}/stream` | SSE stream of real-time events |
| `POST` | `/api/workflows/{id}/skills/{skill_id}` | Install skill into workflow |
| `DELETE` | `/api/workflows/{id}/skills/{skill_id}` | Remove skill from workflow |

---

## Providers

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/providers` | Register provider |
| `GET` | `/api/providers` | List providers |
| `GET` | `/api/providers/{id}` | Get provider |
| `PUT` | `/api/providers/{id}` | Update provider |
| `DELETE` | `/api/providers/{id}` | Delete provider |

---

## Tokens

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tokens` | Store encrypted token |
| `GET` | `/api/tokens` | List tokens (values hidden) |
| `DELETE` | `/api/tokens/{id}` | Delete token |

---

## Guardrails

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/guardrails` | Create guardrail |
| `GET` | `/api/guardrails` | List guardrails |
| `GET` | `/api/guardrails/{id}` | Get guardrail |
| `PUT` | `/api/guardrails/{id}` | Update guardrail |
| `DELETE` | `/api/guardrails/{id}` | Delete guardrail |

---

## Models

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/models` | List available models |

---

## Tasks

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tasks` | List task executions (optional `?workflow_id=`) |
| `GET` | `/api/tasks/{id}` | Get task execution |

---

## SSE Event Types

When connected to `GET /api/workflows/{id}/stream`, the following event types are received:

| Event Type | Payload | Description |
|---|---|---|
| `log` | `{event, detail}` | Agent lifecycle events |
| `message` | `{role, content}` | Complete assistant/tool message |
| `message_delta` | `{delta}` | Streaming token fragment |
| `usage` | `{total_in, total_out, cost...}` | Cumulative usage stats |
| `status` | `{status, current_turn}` | Workflow state changes |

### Connecting via JavaScript

```javascript
const es = new EventSource('/api/workflows/<WF_ID>/stream');
es.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  // type: log | message | message_delta | usage | status
};
```

!!! tip "Interactive API docs"
    The Swagger UI at [http://localhost:8000/docs](http://localhost:8000/docs) provides a fully interactive API explorer with request/response schemas.
