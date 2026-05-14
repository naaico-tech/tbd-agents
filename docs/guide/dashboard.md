# Dashboard

The Flutter dashboard is the primary user interface for TBD Agents. In the Docker image it is built with `--base-href /dashboard/` and served by FastAPI at:

- **Flutter dashboard:** `http://localhost:8000/dashboard`
- **Legacy dashboard:** `http://localhost:8000/dashboard-legacy`
- **Swagger UI:** `http://localhost:8000/docs`

## Sidebar Navigation

| Page | Use it for |
|---|---|
| Dashboard | High-level status and counts |
| Agents | Create agents, select models/providers, and attach MCP servers, custom tools, built-in tools, and knowledge |
| MCP Servers | Register, test, inspect, update, and delete MCP servers |
| Custom Tools | View bundled plugins and user-defined tools; map stored tokens to required environment variables |
| Skills | Manage reusable instruction blocks |
| Knowledge | Manage UI knowledge source/item forms and API-backed knowledge records |
| Guardrails | Configure prompt, request, and output policies |
| Tokens | Store encrypted credentials and view masked values |
| Providers | Configure BYOK providers |
| Workflows | Build runnable agent templates with skills, guardrails, memory, repository, and webhook settings |
| Scheduled Agents | Run workflow prompts on a recurring cadence |
| Task Executions | Monitor runs, inspect details/logs/usage, filter by workflow, and stop active tasks |
| Run Task | Submit a prompt to a workflow with an optional reasoning-effort override |
| Chat | Stream conversational messages with a selected agent |

## UI vs API Coverage

The dashboard covers the common operational workflow, but some API capabilities remain automation-only. For example, custom tool creation/upload and knowledge file upload are available through the REST API even when the dashboard only shows list, mapping, or text-entry flows.

Use the API reference when you need scripting, bulk import/export, or fields that are not exposed in the current forms.

