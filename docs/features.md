# Features

TBD Agents combines a self-hosted control plane, distributed agent execution, and a Flutter dashboard.

## Dashboard Surfaces

The current Flutter UI is served at `/dashboard` and exposes these pages:

| Page | What it does |
|---|---|
| Dashboard | High-level counts and status |
| Agents | Agent CRUD, model/provider selection, MCP/custom/knowledge/built-in tool assignment |
| MCP Servers | Register, test, inspect, update, and delete MCP servers |
| Custom Tools | View bundled plugin/user tools, enabled state, schemas, environment requirements, and token mappings |
| Skills | Manage reusable instruction modules |
| Knowledge | Manage UI knowledge source/item forms and API-backed source/item records |
| Guardrails | Prompt/request/output policy configuration |
| Tokens | Encrypted credential store with masked values |
| Providers | BYOK provider configuration |
| Workflows | Agent execution templates, skills, guardrails, memory, repo, and webhook settings |
| Scheduled Agents | Recurring workflow prompts |
| Task Executions | History, filters, details, logs, usage, and stop controls |
| Run Task | Submit a prompt to a selected workflow with optional reasoning effort override |
| Chat | Stream conversational messages with a selected agent |

## Core Capabilities

- **Agents** with system prompts, models, providers, MCP servers/tags, custom tools, knowledge sources/tags, and built-in tools (`bash`, `read`, `write`, `edit`, `glob`, `grep`, `web_fetch`, `web_search`).
- **Workflows** with model overrides, max turns, output format, reasoning effort, skills, guardrails, infinite session, memory options, TSV tool results, caveman mode, repo checkout settings, credential overrides, and webhooks.
- **Distributed execution** through FastAPI, Redis, Celery workers, and task history.
- **Scheduled agents** for repeated workflow prompts.
- **Memory and knowledge** using Redis STM, MongoDB/PostgreSQL LTM, Qdrant, and pgvector.
- **Import/export** JSON bundles through API endpoints; the Flutter UI exposes Agents, Skills, and Workflows.
