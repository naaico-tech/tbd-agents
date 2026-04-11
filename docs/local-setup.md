# Local Setup

This guide covers running TBD Agent on your development machine — both the Docker path and the bare-metal path.

## Prerequisites

| Requirement | Why |
|---|---|
| **Docker & Docker Compose** | Fastest way to start — runs the API, workers, MongoDB, and Redis in one command |
| **GitHub PAT** with `copilot` scope | Authenticates agent sessions against the Copilot SDK ([create one here](https://github.com/settings/tokens)) |
| **GitHub Copilot subscription** | Individual, Business, or Enterprise — billing goes through premium request quotas |
| **Node.js 22+** | Required by `npx`-based MCP servers (included automatically in the Docker image) |
| **Python 3.12+** | Only needed for bare-metal development |

## Option 1 — Docker Compose (recommended)

```bash
git clone <repo-url> && cd tbd-agents

# Create your environment file
cp .env.example .env
# Edit .env and fill in at least GITHUB_TOKEN

docker-compose up --build
```

This starts four services:

| Service | Port | Description |
|---|---|---|
| `app` | 8000 | FastAPI API + dashboard |
| `worker` | — | Celery worker (4 concurrent agent slots) |
| `redis` | 6379 | Task broker + event bus |
| `mongodb` | 27017 | Persistent storage |

- **Dashboard:** http://localhost:8000/dashboard
- **Swagger docs:** http://localhost:8000/docs
- **API base:** http://localhost:8000/api

### Scaling workers

```bash
# Run 3 worker containers instead of 1
docker-compose up --build --scale worker=3
```

Each worker defaults to `--concurrency=4`, so 3 containers = 12 concurrent agent executions.

## Option 2 — Bare Metal

### 1. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Start infrastructure

You need MongoDB and Redis running locally. The easiest way:

```bash
# MongoDB
docker run -d --name mongo -p 27017:27017 mongo:7

# Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Or install them natively via `brew install mongodb-community redis` (macOS) or your package manager.

### 3. Set environment variables

```bash
export MONGO_URI=mongodb://localhost:27017
export REDIS_URL=redis://localhost:6379/0
export GITHUB_TOKEN="ghp_your_token_here"
```

Or create a `.env` file — Pydantic Settings loads it automatically.

### 4. Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Start a Celery worker

In a separate terminal (same virtualenv):

```bash
celery -A app.celery_app worker --loglevel=info --concurrency=4
```

The API and worker are now running. Send prompts via the API or dashboard and they will be picked up by the Celery worker.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `copilot_agent_hub` | Database name |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL for Celery broker/backend and event pub/sub |
| `DEFAULT_MODEL` | `gpt-4.1` | Default model for new workflows |
| `DEFAULT_MAX_TURNS` | `5` | Default max tool-call turns per workflow |
| `SESSION_TIMEOUT` | `300` | SDK session timeout in seconds |
| `GITHUB_TOKEN` | — | Server-level GitHub PAT (per-request Bearer tokens take priority) |
| `NOTION_TOKEN` | — | Notion integration token for auto-injected Notion MCP |
| `SLACK_BOT_TOKEN` | — | Slack bot token for auto-injected Slack MCP |
| `DD_API_KEY` | — | Datadog API key |
| `DD_APP_KEY` | — | Datadog App key |
| `DD_SITE` | `datadoghq.com` | Datadog site |
| `ATLASSIAN_API_TOKEN` | — | Atlassian API token |
| `ATLASSIAN_EMAIL` | — | Atlassian account email |
| `ATLASSIAN_URL` | — | Atlassian site URL |

## Verifying the setup

```bash
# Health check
curl http://localhost:8000/health

# Create a simple agent
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "system_prompt": "You are a helpful assistant."}'

# Check the dashboard
open http://localhost:8000/dashboard
```

## Troubleshooting

| Problem | Solution |
|---|---|
| `Connection refused` on port 8000 | Ensure `uvicorn` or the `app` container is running |
| `Connection refused` on Redis/Mongo | Start the infrastructure containers or native services |
| Workers not picking up tasks | Verify `REDIS_URL` matches between API and worker; check `celery -A app.celery_app inspect active` |
| MCP server fails to start | Ensure Node.js 22+ is installed; MCP servers use `npx` which requires it |
| `copilot` scope errors | Regenerate your GitHub PAT with the `copilot` scope enabled |
