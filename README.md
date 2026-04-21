<p align="center">

```
████████╗██████╗ ██████╗      █████╗  ██████╗ ███████╗███╗   ██╗████████╗
╚══██╔══╝██╔══██╗██╔══██╗    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
   ██║   ██████╔╝██║  ██║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
   ██║   ██╔══██╗██║  ██║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
   ██║   ██████╔╝██████╔╝    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
   ╚═╝   ╚═════╝ ╚═════╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
```

</p>

<p align="center">
  <em>▓▓ Your agents. Your rules. Your infrastructure. ▓▓</em><br>
  <sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub>
</p>

<p align="center">
  ⚡ Built by <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⚡
</p>

---

```
╔══════════════════════════════════════════════════════════════════════╗
║  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ║
║  ░  TBD Agent lets you build, control, and trigger your own     ░  ║
║  ░  custom AI agents over the web — no black boxes, no vendor   ░  ║
║  ░  lock-in, just a clean API backed by the GitHub Copilot SDK  ░  ║
║  ░  that you run on your own infrastructure.                    ░  ║
║  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ║
╚══════════════════════════════════════════════════════════════════════╝
```

Spin up purpose-built agents with distinct system prompts, wire them to any MCP tool server, send a prompt over HTTP, and watch them work in real-time through streaming Server-Sent Events. Need to scale? Celery workers distribute agent execution across as many nodes as you want.

> 🎮 **TBD** — *To Be Decided* by you: what your agents do, which tools they use, and how far they go.

---

## ★ Highlights

```
┌─────────────────────────────────────────────────────────────────────┐
│  ██ POWER-UPS UNLOCKED ██                                          │
└─────────────────────────────────────────────────────────────────────┘
```

- 🏠 **Fully self-hosted** — runs on your infra via Docker Compose; no SaaS dependency beyond GitHub Copilot billing
- 🤖 **Custom agents over HTTP** — create, configure, and trigger agents with a simple REST API or the built-in dashboard
- ⚡ **Real-time streaming** — SSE endpoint streams logs, messages, token-by-token responses, and usage metrics live to any client
- 🔀 **Distributed workers** — Celery + Redis architecture lets you scale agent execution horizontally; add workers to handle load
- 🔧 **MCP tool ecosystem** — connect any MCP-compatible tool server (Datadog, Jira, Notion, Slack, and hundreds more) via stdio or SSE
- ♾️ **Infinite sessions** — automatic context compaction keeps long-running agents alive without hitting context limits
- 📊 **Usage & cost tracking** — per-workflow token counts, premium request quotas, and cost data from the Copilot SDK
- 🧩 **Skills system** — modular instruction sets that can be installed per workflow to shape agent behaviour
- 📤 **Output destinations** — agents autonomously decide when to push results to Notion pages or Slack channels
- 📚 **Knowledge bases** — attach vector databases (Qdrant) or upload files/text tagged for retrieval; agents pull relevant knowledge into their context automatically

---

## 🚀 Quick Start

```
 ╔═══════════════════════════════╗
 ║  PRESS START ► ► ► ► ► ► ►  ║
 ╚═══════════════════════════════╝
```

```bash
git clone <repo-url> && cd tbd-agents

# Create your environment file and fill in at least GITHUB_TOKEN
cp .env.example .env

docker-compose up --build
```

Your GitHub PAT needs the `copilot` scope — [create one here](https://github.com/settings/tokens).

```
 ┌──────────────────────────────────────────────────┐
 │  ► Dashboard ─── http://localhost:8000/dashboard  │
 │  ► API docs  ─── http://localhost:8000/docs       │
 │  ► API base  ─── http://localhost:8000/api        │
 └──────────────────────────────────────────────────┘
```

See [docs/local-setup.md](docs/local-setup.md) for detailed local development instructions.

---

## 📖 Documentation

```
 ╔═══════════════════════════════════════╗
 ║  SELECT YOUR QUEST                    ║
 ╠═══════════════════════════════════════╣
 ║                                       ║
 ║  [1] Local Setup                      ║
 ║  [2] Architecture                     ║
 ║  [3] Features                         ║
 ║  [4] Contributing                     ║
 ║                                       ║
 ╚═══════════════════════════════════════╝
```

| Document | Description |
|---|---|
| [Local Setup](docs/local-setup.md) | Prerequisites, Docker and bare-metal setup, environment variables |
| [Architecture](docs/architecture.md) | System design, distributed worker flow, Redis event bus, data model |
| [Features](docs/features.md) | Deep dive into agents, MCP, skills, streaming, infinite sessions, and more |
| [Contributing](CONTRIBUTING.md) | How to contribute: setup, coding standards, PR guidelines |

---

## 🔌 API Reference

> All endpoints (except `/health`) require `Authorization: Bearer <GITHUB_TOKEN>` header.

### ♥ Health

```
GET /health
```

### 🤖 Agents

```
POST   /api/agents              ← Create agent
GET    /api/agents              ← List agents
GET    /api/agents/{id}         ← Get agent
PUT    /api/agents/{id}         ← Update agent
DELETE /api/agents/{id}         ← Delete agent
```

### 🧩 Skills

```
POST   /api/skills              ← Create skill
GET    /api/skills              ← List skills
GET    /api/skills/{id}         ← Get skill
PUT    /api/skills/{id}         ← Update skill
DELETE /api/skills/{id}         ← Delete skill
```

### 🔧 MCP Servers

```
POST   /api/mcps                ← Register MCP server
GET    /api/mcps                ← List MCP servers
GET    /api/mcps/{id}           ← Get MCP server
POST   /api/mcps/{id}/test      ← Test MCP connection
GET    /api/mcps/{id}/tools     ← List tools from MCP server
DELETE /api/mcps/{id}           ← Remove MCP server
```

### 📚 Knowledge Sources

```
POST   /api/knowledge-sources              ← Register knowledge source (vector_db or mongo_db)
GET    /api/knowledge-sources              ← List sources (optional ?tags= filter)
GET    /api/knowledge-sources/{id}         ← Get source
PUT    /api/knowledge-sources/{id}         ← Update source
DELETE /api/knowledge-sources/{id}         ← Delete source (cascade-deletes items)
POST   /api/knowledge-sources/{id}/test    ← Test connection
```

### 📄 Knowledge Items

```
POST   /api/knowledge-items                ← Create text knowledge item
POST   /api/knowledge-items/upload         ← Upload file/image (multipart)
GET    /api/knowledge-items                ← List items (?source_id=, ?tags=, ?content_type=)
GET    /api/knowledge-items/{id}           ← Get item metadata
GET    /api/knowledge-items/{id}/content   ← Download file content
PUT    /api/knowledge-items/{id}           ← Update item tags/metadata
DELETE /api/knowledge-items/{id}           ← Delete item
POST   /api/knowledge-items/query          ← Query items by tags
```

### ⚙️ Workflows

```
POST   /api/workflows                        ← Create workflow
POST   /api/workflows/{id}/prompt            ← Send prompt (returns 201, runs via worker)
GET    /api/workflows/{id}                   ← Get workflow state + logs + messages
GET    /api/workflows/{id}/stream            ← SSE stream of real-time events
GET    /api/workflows                        ← List your workflows
POST   /api/workflows/{id}/skills/{skill_id} ← Install skill into workflow
DELETE /api/workflows/{id}/skills/{skill_id} ← Remove skill from workflow
```

---

## 🕹️ Usage Examples

### ► Stage 1 — Create an Agent

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

### ► Stage 2 — Register an MCP Server

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

### ► Stage 3 — Create a Workflow and Send a Prompt

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
    "caveman": true,
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

### ► Stage 4 — Stream Results in Real-Time

```bash
curl -N "http://localhost:8000/api/workflows/$WORKFLOW_ID/stream"
```

### ► Stage 5 — Add a Knowledge Base

```bash
# Register a local MongoDB-backed knowledge source
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "product-docs",
    "source_type": "mongo_db",
    "tags": ["docs", "product"]
  }'

# Upload a text knowledge item tagged for retrieval
curl -X POST http://localhost:8000/api/knowledge-items \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "<SOURCE_ID>",
    "name": "API rate limits",
    "content_type": "text",
    "text_content": "Rate limit is 1000 req/min per API key. Burst limit is 50 req/s.",
    "tags": ["docs", "api"]
  }'

# Upload a file via multipart form
curl -X POST http://localhost:8000/api/knowledge-items/upload \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -F "file=@architecture.pdf" \
  -F "source_id=<SOURCE_ID>" \
  -F 'tags=["docs", "architecture"]'

# Attach knowledge to an agent by tags
curl -X PUT http://localhost:8000/api/agents/<AGENT_ID> \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"knowledge_tags": ["docs"]}'
```

### ► Stage 6 — Connect a Qdrant Vector Database

To use an external Qdrant instance as a knowledge source:

```bash
# 1. Store the Qdrant API key in the encrypted token store
curl -X POST http://localhost:8000/api/tokens \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "qdrant-api-key",
    "value": "your-qdrant-api-key-here",
    "description": "Qdrant Cloud API key"
  }'

# 2. Register the Qdrant source
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "qdrant-docs",
    "source_type": "vector_db",
    "connection_config": {
      "url": "https://your-cluster.qdrant.io:6333",
      "collection": "documents",
      "api_key_token_name": "qdrant-api-key"
    },
    "tags": ["vector", "docs"]
  }'

# 3. Test the connection
curl -X POST http://localhost:8000/api/knowledge-sources/<SOURCE_ID>/test \
  -H "Authorization: Bearer $GITHUB_TOKEN"

# 4. Attach to an agent by ID or tags
curl -X PUT http://localhost:8000/api/agents/<AGENT_ID> \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"knowledge_source_ids": ["<SOURCE_ID>"]}'
```

For local development, uncomment the `qdrant` service in `docker-compose.yml` and use `http://qdrant:6333` as the URL.

---

## 🧠 Supported Models

```
 ┌─────────────────────────────────────────────────┐
 │  ▓▓ MODEL SELECT ▓▓                             │
 │                                                  │
 │  ► gpt-4.1  ► gpt-4.1-mini  ► gpt-4.1-nano     │
 │  ► gpt-4o   ► gpt-4o-mini                       │
 │  ► o3       ► o3-mini       ► o4-mini            │
 │  ► claude-sonnet-4.5 (if available via Copilot)  │
 │                                                  │
 └─────────────────────────────────────────────────┘
```

Any model available through GitHub Copilot is supported.

---

## 🏗️ Tech Stack

```
 ┌────────────────┬───────────────────────────────────┐
 │  ░░ COMPONENT  │  ░░ TECHNOLOGY                    │
 ├────────────────┼───────────────────────────────────┤
 │  API           │  FastAPI + Uvicorn                │
 │  Agent engine  │  GitHub Copilot SDK (JSON-RPC)    │
 │  Task queue    │  Celery + Redis                   │
 │  Event bus     │  Redis Pub/Sub                    │
 │  Database      │  MongoDB + Beanie ODM             │
 │  Vector DB     │  Qdrant (optional, for knowledge)  │
 │  Frontend      │  Single-page dashboard (JS, SSE)  │
 │  Containers    │  Docker Compose                   │
 └────────────────┴───────────────────────────────────┘
```

---

## 📜 License

MIT

---

```
═══════════════════════════════════════════════════════════════════
```

<p align="center">

```
 ███╗   ██╗ █████╗  █████╗ ██╗ ██████╗ ██████╗
 ████╗  ██║██╔══██╗██╔══██╗██║██╔════╝██╔═══██╗
 ██╔██╗ ██║███████║███████║██║██║     ██║   ██║
 ██║╚██╗██║██╔══██║██╔══██║██║██║     ██║   ██║
 ██║ ╚████║██║  ██║██║  ██║██║╚██████╗╚██████╔╝
 ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═════╝
```

</p>

<p align="center">
  ⬛⬜⬛ A <a href="https://www.naaico.com"><strong>NAAICO</strong></a> Product ⬛⬜⬛
</p>
