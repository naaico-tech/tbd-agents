<p align="center">
  <strong>TBD Agent</strong><br>
  <em>Your agents. Your rules. Your infrastructure.</em>
</p>

<p align="center">
  Built by <a href="https://www.naaico.com">NAAICO</a>
</p>

---

**TBD Agent** lets you build, control, and trigger your own custom AI agents over the web — no black boxes, no vendor lock-in, just a clean API backed by the **GitHub Copilot SDK** that you run on your own infrastructure.

Spin up purpose-built agents with distinct system prompts, wire them to any MCP tool server, send a prompt over HTTP, and watch them work in real-time through streaming Server-Sent Events. Need to scale? Celery workers distribute agent execution across as many nodes as you want.

> **TBD** — *To Be Decided* by you: what your agents do, which tools they use, and how far they go.

## Highlights

- **Fully self-hosted** — runs on your infra via Docker Compose; no SaaS dependency beyond GitHub Copilot billing
- **Custom agents over HTTP** — create, configure, and trigger agents with a simple REST API or the built-in dashboard
- **Real-time streaming** — SSE endpoint streams logs, messages, token-by-token responses, and usage metrics live to any client
- **Distributed workers** — Celery + Redis architecture lets you scale agent execution horizontally; add workers to handle load
- **MCP tool ecosystem** — connect any MCP-compatible tool server (Datadog, Jira, Notion, Slack, and hundreds more) via stdio or SSE
- **Infinite sessions** — automatic context compaction keeps long-running agents alive without hitting context limits
- **Usage & cost tracking** — per-workflow token counts, premium request quotas, and cost data from the Copilot SDK
- **Skills system** — modular instruction sets that can be installed per workflow to shape agent behaviour
- **Output destinations** — agents autonomously decide when to push results to Notion pages or Slack channels

## Quick Start

```bash
git clone <repo-url> && cd tbd-agents

# Set your GitHub PAT (requires `copilot` scope)
export GITHUB_TOKEN="ghp_your_token_here"

docker-compose up --build
```

- **Dashboard:** http://localhost:8000/dashboard
- **API docs:** http://localhost:8000/docs
- **API base:** http://localhost:8000/api

See [docs/local-setup.md](docs/local-setup.md) for detailed local development instructions.

## Documentation

| Document | Description |
|---|---|
| [Local Setup](docs/local-setup.md) | Prerequisites, Docker and bare-metal setup, environment variables |
| [Architecture](docs/architecture.md) | System design, distributed worker flow, Redis event bus, data model |
| [Features](docs/features.md) | Deep dive into agents, MCP, skills, streaming, infinite sessions, and more |
| [GitHub Settings Guide](docs/github-settings-guide.md) | Repository configuration for open source with controlled access |
| [Contributing](CONTRIBUTING.md) | How to contribute: setup, coding standards, PR guidelines |

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
POST   /api/workflows/{id}/prompt            — Send prompt (returns 201, runs via worker)
GET    /api/workflows/{id}                   — Get workflow state + logs + messages
GET    /api/workflows/{id}/stream            — SSE stream of real-time events
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

### 3. Create a Workflow and Send a Prompt

```bash
# Create workflow with Notion output + infinite session
WORKFLOW=$(curl -s -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "max_turns": 10,
    "output_format": "markdown",
    "infinite_session": true,
    "output_destination": {
      "notion_base_page_id": "abc123..."
    }
  }')

WORKFLOW_ID=$(echo "$WORKFLOW" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

# Send prompt — dispatched to a Celery worker
curl -X POST "http://localhost:8000/api/workflows/$WORKFLOW_ID/prompt" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Investigate the spike in p99 latency on the payments service over the last 24 hours."}'
```

### 4. Stream Results in Real-Time

```bash
curl -N "http://localhost:8000/api/workflows/$WORKFLOW_ID/stream"
```

## Supported Models

Any model available through GitHub Copilot, including:
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`
- `gpt-4o`, `gpt-4o-mini`
- `o3`, `o3-mini`, `o4-mini`
- `claude-sonnet-4.5` (if available via Copilot)

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Agent engine | GitHub Copilot SDK (JSON-RPC) |
| Task queue | Celery + Redis |
| Event bus | Redis Pub/Sub |
| Database | MongoDB + Beanie ODM |
| Frontend | Single-page dashboard (vanilla JS, SSE) |
| Containerisation | Docker Compose |

## License

MIT

---

<p align="center">A <a href="https://www.naaico.com">NAAICO</a> product</p>
