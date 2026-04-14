# Quick Start

Get TBD Agents running in under 5 minutes with Docker Compose.

---

## Prerequisites

- **Docker & Docker Compose** installed
- **GitHub PAT** with the `copilot` scope — [create one here](https://github.com/settings/tokens)
- **GitHub Copilot subscription** (Individual, Business, or Enterprise)

---

## 1. Clone and configure

```bash
git clone https://github.com/naaico-tech/tbd-agents.git && cd tbd-agents
cp .env.example .env
# Edit .env and set at least GITHUB_TOKEN
```

## 2. Start the stack

```bash
docker-compose up --build
```

This starts four services:

| Service | Port | Description |
|---|---|---|
| `app` | 8000 | FastAPI API + dashboard |
| `worker` | — | Celery worker (4 concurrent slots) |
| `redis` | 6379 | Task broker + event bus |
| `mongodb` | 27017 | Persistent storage |

!!! tip "Access points"
    - **Dashboard** — [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
    - **Swagger UI** — [http://localhost:8000/docs](http://localhost:8000/docs)
    - **API base** — [http://localhost:8000/api](http://localhost:8000/api)

## 3. Create an agent

```bash
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code-reviewer",
    "system_prompt": "You are an expert code reviewer.",
    "model": "gpt-4.1"
  }'
```

## 4. Create a workflow and send a prompt

```bash
# Create workflow
WORKFLOW=$(curl -s -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "max_turns": 10,
    "output_format": "markdown"
  }')

WORKFLOW_ID=$(echo "$WORKFLOW" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

# Send prompt
curl -X POST "http://localhost:8000/api/workflows/$WORKFLOW_ID/prompt" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Review the code in the main module for security issues."}'
```

## 5. Stream results in real-time

```bash
curl -N "http://localhost:8000/api/workflows/$WORKFLOW_ID/stream"
```

---

## What's next?

- [Local Setup](local-setup.md) — bare-metal development, environment variables, troubleshooting
- [Guide](../guide/index.md) — deep dive into agents, MCP tools, skills, streaming, and more
- [Architecture](../architecture/index.md) — system design and scaling guide
