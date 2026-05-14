# Agents

Agents are reusable profiles that define what an assistant is, which model/provider it uses, and which context/tools it can access.

## Dashboard Fields

| Field | Description |
|---|---|
| Name | Human-readable unique name |
| Description | Optional summary shown in lists |
| System prompt | Core behavioral instructions |
| Model | Model identifier; workflows may override it |
| Provider | Optional BYOK provider; unset uses the default GitHub/Copilot path |
| MCP servers | Explicit MCP server IDs |
| MCP tags | Include any MCP server with matching tags |
| Custom tools | Explicit custom tool IDs; bundled plugins and user tools appear in the selector |
| Knowledge sources | Explicit source IDs |
| Knowledge tags | Include matching knowledge sources/items at runtime |
| Built-in tools | Enable `bash`, `read`, `write`, `edit`, `glob`, `grep`, `web_fetch`, or `web_search` |

MCP server IDs and tags are unioned and de-duplicated. Knowledge source IDs and tags work the same way for context retrieval.

## API Example

```bash
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "incident-responder",
    "description": "Investigates production alerts",
    "system_prompt": "You are an SRE investigating production incidents.",
    "model": "gpt-4.1",
    "mcp_server_tags": ["observability"],
    "knowledge_tags": ["runbook"],
    "builtin_tools": ["bash", "grep", "web_search"]
  }'
```

## Custom Tool Lock-in

Custom tools are attached by `custom_tool_ids`. Disabled tools are skipped at runtime. Plugins loaded from `app/plugins.yaml` are exposed as custom tools with `is_plugin: true` and cannot be authored in the dashboard.

## Chat vs Tasks

Use **Chat** for conversational Q&A with an agent. Use **Run Task** or the workflow prompt API when you need asynchronous tool-using task execution and task history.
