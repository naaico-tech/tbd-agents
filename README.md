# Copilot Agent Hub

Multi-agent API hub powered by the **official GitHub Copilot SDK** with native MCP (Model Context Protocol) tool support.

## What Changed in v0.2

This project was revamped from raw `httpx` calls to the GitHub Models API to the **official `github-copilot-sdk`** Python package. The SDK:

- Spawns the bundled Copilot CLI and communicates via JSON-RPC
- Handles the full agentic loop (planning → tool calls → response) natively
- Connects to MCP servers directly (no more ephemeral reconnection per tool call)
- Supports streaming, infinite sessions, and context-window compaction
- Billing goes through GitHub Copilot premium request quota

## Features

- **Multi-Agent System** — Create custom agents with distinct system prompts, models, and MCP configurations
- **GitHub Copilot SDK** — Full agentic loop handled natively (tool planning, execution, response generation)
- **MCP Integration** — Connect external MCP servers (stdio or SSE); the SDK manages persistent connections during sessions
- **Skills** — Installable instruction sets injected into the system prompt per workflow
- **Async Execution** — Prompts return 201 immediately; poll the workflow for progress and logs
- **Max Turns** — Configurable limit on tool-call rounds per workflow (enforced via permission handler)
- **Output Formats** — JSON or Markdown responses
- **MongoDB Storage** — Persistent agent configs, MCP registrations, skills, and workflow history
- **Dockerized** — Single `docker-compose up` for the full stack

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A GitHub Personal Access Token with `copilot` scope ([create one here](https://github.com/settings/tokens))
- A **GitHub Copilot subscription** (Individual, Business, or Enterprise)

### Run

```bash
# Clone and start
git clone <repo-url> && cd copilot-agent-hub
export GITHUB_TOKEN="ghp_your_token_here"
docker-compose up --build
```

The API is available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Local Development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start MongoDB locally (or use a cloud instance)
export MONGO_URI=mongodb://localhost:27017
export GITHUB_TOKEN="ghp_your_token_here"

uvicorn app.main:app --reload
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `copilot_agent_hub` | Database name |
| `DEFAULT_MODEL` | `gpt-4.1` | Default model for new workflows |
| `DEFAULT_MAX_TURNS` | `5` | Default max tool-call turns per workflow |
| `SESSION_TIMEOUT` | `300` | SDK session timeout in seconds |
| `GITHUB_TOKEN` | — | Optional server-level token (per-request Bearer tokens take priority) |
| `DD_API_KEY` | — | Datadog API key (for Datadog MCP) |
| `DD_APP_KEY` | — | Datadog App key (for Datadog MCP) |
| `DD_SITE` | `datadoghq.com` | Datadog site |
| `ATLASSIAN_API_TOKEN` | — | Atlassian API token (for Jira MCP) |
| `ATLASSIAN_EMAIL` | — | Atlassian account email |
| `ATLASSIAN_URL` | — | Atlassian site URL |

## API Reference

All endpoints (except `/health`) require `Authorization: Bearer <GITHUB_TOKEN>` header.

### Health

```
GET /health
```

### Agents

```
POST   /api/agents              — Create agent
GET    /api/agents              — List agents
GET    /api/agents/{id}         — Get agent
PUT    /api/agents/{id}         — Update agent
DELETE /api/agents/{id}         — Delete agent
```

### Skills

```
POST   /api/skills              — Create skill
GET    /api/skills              — List skills
GET    /api/skills/{id}         — Get skill
PUT    /api/skills/{id}         — Update skill
DELETE /api/skills/{id}         — Delete skill
```

### MCP Servers

```
POST   /api/mcps                — Register MCP server
GET    /api/mcps                — List MCP servers
GET    /api/mcps/{id}           — Get MCP server
POST   /api/mcps/{id}/test      — Test MCP connection
GET    /api/mcps/{id}/tools     — List tools from MCP server
DELETE /api/mcps/{id}           — Remove MCP server
```

### Workflows

```
POST   /api/workflows                        — Create workflow
POST   /api/workflows/{id}/prompt            — Send prompt (returns 201, runs async)
GET    /api/workflows/{id}                   — Poll workflow state + logs
GET    /api/workflows                        — List your workflows
POST   /api/workflows/{id}/skills/{skill_id} — Install skill into workflow
DELETE /api/workflows/{id}/skills/{skill_id} — Remove skill from workflow
```

## Usage Examples

### 1. Create an Agent

```bash
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code-reviewer",
    "system_prompt": "You are an expert code reviewer. Analyze code for bugs, security issues, and improvements.",
    "model": "gpt-4.1"
  }'
```

### 2. Register an MCP Server

```bash
# Stdio-based MCP server (e.g., Datadog)
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "datadog",
    "transport_type": "stdio",
    "connection_config": {
      "command": "npx",
      "args": ["-y", "@datadog/mcp-server-datadog"],
      "env": {"DD_API_KEY": "...", "DD_APP_KEY": "...", "DD_SITE": "datadoghq.com"}
    }
  }'
```

### 3. Attach MCP to Agent

```bash
curl -X PUT http://localhost:8000/api/agents/<AGENT_ID> \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mcp_server_ids": ["<MCP_ID>"]}'
```

### 4. Create a Workflow and Send a Prompt

```bash
# Create workflow
WORKFLOW=$(curl -s -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "<AGENT_ID>", "max_turns": 5, "output_format": "json"}')

WORKFLOW_ID=$(echo "$WORKFLOW" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

# Send prompt (returns 201 immediately)
curl -X POST "http://localhost:8000/api/workflows/$WORKFLOW_ID/prompt" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?"}'

# Poll for results
curl "http://localhost:8000/api/workflows/$WORKFLOW_ID" \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Client (curl / app / CI)                        │
│  Authorization: Bearer <GitHub PAT>              │
└──────────────┬───────────────────────────────────┘
               │
       ┌───────▼────────┐
       │   FastAPI App   │
       │   /api/...      │
       └───────┬────────┘
               │
  ┌────────────┼────────────────┐
  │            │                │
  ▼            ▼                ▼
Agents DB   Workflows DB    MCP Servers DB
(MongoDB)   (MongoDB)       (MongoDB)
               │
       ┌───────▼────────────┐
       │  Copilot SDK Client │
       │  (JSON-RPC)         │
       └──┬──────────────┬──┘
          │              │
          ▼              ▼
  Copilot CLI         MCP Servers
  (bundled)           (stdio/sse)
      │
      ▼
  GitHub Copilot
  Models API
```

## Supported Models

Any model available through GitHub Copilot, including:
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`
- `gpt-4o`, `gpt-4o-mini`
- `o3`, `o3-mini`, `o4-mini`
- `claude-sonnet-4.5` (if available via Copilot)

## License

MIT
