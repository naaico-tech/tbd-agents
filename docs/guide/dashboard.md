# Dashboard

The primary Flutter dashboard is served at:

```text
http://localhost:8000/dashboard
```

The legacy static dashboard is available at `/dashboard-legacy`. `/dashboard-new-ui` remains a compatibility alias for legacy UI routing and should not be documented as the primary Flutter URL.

## Sidebar Pages

| Page | Purpose |
|---|---|
| Dashboard | Overview counts and service state |
| Agents | Create and update agent profiles, models, providers, tools, MCP tags, and knowledge tags |
| MCP Servers | Register, update, test, and inspect allowed tools for MCP servers |
| Custom Tools | View bundled plugins and user tools, enabled state, schemas, environment requirements, and token mappings |
| Skills | Create reusable instruction modules and import/export skill bundles |
| Knowledge | Create source/item records through the UI forms; advanced file/GridFS operations remain API-first |
| Guardrails | Configure prompt, request, and output policies |
| Tokens | Store encrypted credentials and see masked values only |
| Providers | Configure BYOK/OpenAI-compatible/Anthropic providers |
| Workflows | Create execution templates with skills, guardrails, memory, repo, and webhook settings |
| Scheduled Agents | Schedule recurring workflow prompts |
| Task Executions | Filter history, inspect prompt/response/usage/conversation/logs, and stop active tasks |
| Run Task | Select a workflow, enter a prompt, optionally override reasoning effort, run or stop |
| Chat | Pick an agent and stream conversational messages in the current in-memory session |

## Common Flow

1. Add credentials in **Tokens** if an MCP server, provider, repo, or plugin needs secrets.
2. Configure **Providers** if you are using BYOK instead of the default GitHub/Copilot path.
3. Register **MCP Servers**, review **Custom Tools**, and add **Skills** or **Knowledge**.
4. Create an **Agent** and assign tools/knowledge by ID or tag.
5. Create a **Workflow** for that agent.
6. Use **Run Task**, **Task Executions**, **Scheduled Agents**, or **Chat** depending on whether you need asynchronous task execution, recurring prompts, or conversational Q&A.

## Import/Export Limitations

The Flutter UI currently exposes import/export buttons for **Agents**, **Skills**, and **Workflows**. Full-system and knowledge-source import/export endpoints are available through the API; see [Import & Export](import-export.md).
