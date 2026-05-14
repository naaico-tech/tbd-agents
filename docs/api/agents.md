# Agents API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents` | Create agent |
| `GET` | `/api/agents` | List agents |
| `GET` | `/api/agents/export` | Export all agents |
| `GET` | `/api/agents/{agent_id}/export` | Export one agent |
| `POST` | `/api/agents/import` | Import agent bundle |
| `GET` | `/api/agents/{agent_id}` | Get agent |
| `PUT` | `/api/agents/{agent_id}` | Update agent |
| `DELETE` | `/api/agents/{agent_id}` | Delete agent |

## Fields

`name`, `description`, `system_prompt`, `model`, `mcp_server_ids`, `mcp_server_tags`, `tool_definitions`, `knowledge_source_ids`, `knowledge_tags`, `builtin_tools`, `custom_tool_ids`, and `provider_id`.

```json
{
  "name": "doc-writer",
  "description": "Writes technical docs",
  "system_prompt": "You write concise technical documentation.",
  "model": "gpt-4.1",
  "mcp_server_tags": ["documentation"],
  "knowledge_tags": ["product"],
  "builtin_tools": ["read", "grep", "web_fetch"]
}
```

Resource-specific import/export is available at the endpoints above; see [Import & Export](import-export.md).
