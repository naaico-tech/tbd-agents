```
██╗      ██████╗  ██████╗ █████╗ ██╗         ███████╗███████╗████████╗██╗   ██╗██████╗
██║     ██╔═══██╗██╔════╝██╔══██╗██║         ██╔════╝██╔════╝╚══██╔══╝██║   ██║██╔══██╗
██║     ██║   ██║██║     ███████║██║         ███████╗█████╗     ██║   ██║   ██║██████╔╝
██║     ██║   ██║██║     ██╔══██║██║         ╚════██║██╔══╝     ██║   ██║   ██║██╔═══╝
███████╗╚██████╔╝╚██████╗██║  ██║███████╗    ███████║███████╗   ██║   ╚██████╔╝██║
╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝    ╚══════╝╚══════╝   ╚═╝    ╚═════╝ ╚═╝
```

<p align="center"><sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub></p>

> 🛠️ This guide covers running TBD Agent on your development machine — both the Docker path and the bare-metal path.

---

## 📋 Prerequisites

```
 ┌──────────────────────────┬──────────────────────────────────────────────────────────────┐
 │  ░░ REQUIREMENT          │  ░░ WHY                                                      │
 ├──────────────────────────┼──────────────────────────────────────────────────────────────┤
 │  Docker & Docker Compose │  Fastest way — runs API, workers, MongoDB, Redis in one cmd  │
 │  GitHub PAT (copilot)    │  Authenticates agent sessions against the Copilot SDK        │
 │  Copilot subscription    │  Individual, Business, or Enterprise — premium request quota  │
 │  Node.js 22+             │  Required by npx-based MCP servers (included in Docker img)  │
 │  Python 3.12+            │  Only needed for bare-metal development                      │
 └──────────────────────────┴──────────────────────────────────────────────────────────────┘
```

[Create a GitHub PAT here →](https://github.com/settings/tokens)

---

## 🐳 Option 1 — Docker Compose (recommended)

```
 ╔═════════════════════════════════════╗
 ║  ► EASY MODE ◄  One command start  ║
 ╚═════════════════════════════════════╝
```

```bash
git clone <repo-url> && cd tbd-agents

# Create your environment file
cp .env.example .env
# Edit .env and fill in at least GITHUB_TOKEN

docker-compose up --build
```

This starts four services:

```
 ┌──────────────┬───────┬───────────────────────────────────────┐
 │  ░░ SERVICE  │  PORT │  ░░ DESCRIPTION                       │
 ├──────────────┼───────┼───────────────────────────────────────┤
 │  app         │  8000 │  FastAPI API + dashboard               │
 │  worker      │   —   │  Celery worker (4 concurrent slots)    │
 │  redis       │  6379 │  Task broker + event bus               │
 │  mongodb     │ 27017 │  Persistent storage                    │
 └──────────────┴───────┴───────────────────────────────────────┘
```

```
 ┌──────────────────────────────────────────────────┐
 │  ► Dashboard ─── http://localhost:8000/dashboard  │
 │  ► Swagger   ─── http://localhost:8000/docs       │
 │  ► API base  ─── http://localhost:8000/api        │
 └──────────────────────────────────────────────────┘
```

### ► Scaling workers

```bash
# Run 3 worker containers instead of 1
docker-compose up --build --scale worker=3
```

Each worker defaults to `--concurrency=4`, so 3 containers = 12 concurrent agent executions.

---

## 🔩 Option 2 — Bare Metal

```
 ╔═════════════════════════════════════╗
 ║  ► HARD MODE ◄  Full control       ║
 ╚═════════════════════════════════════╝
```

### ► Step 1 — Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### ► Step 2 — Start infrastructure

You need MongoDB and Redis running locally. The easiest way:

```bash
# MongoDB
docker run -d --name mongo -p 27017:27017 mongo:7

# Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Or install them natively via `brew install mongodb-community redis` (macOS) or your package manager.

### ► Step 3 — Set environment variables

```bash
export MONGO_URI=mongodb://localhost:27017
export REDIS_URL=redis://localhost:6379/0
export GITHUB_TOKEN="ghp_your_token_here"
```

Or create a `.env` file — Pydantic Settings loads it automatically.

### ► Step 4 — Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

### ► Step 5 — Start a Celery worker

In a separate terminal (same virtualenv):

```bash
celery -A app.celery_app worker --loglevel=info --concurrency=4
```

The API and worker are now running. Send prompts via the API or dashboard and they will be picked up by the Celery worker.

---

## 🔑 Environment Variables

```
 ┌────────────────────┬───────────────────────────┬─────────────────────────────────────────────┐
 │  ░░ VARIABLE       │  ░░ DEFAULT               │  ░░ DESCRIPTION                             │
 ├────────────────────┼───────────────────────────┼─────────────────────────────────────────────┤
 │  MONGO_URI         │  mongodb://mongodb:27017  │  MongoDB connection string                  │
 │  MONGO_DB_NAME     │  copilot_agent_hub        │  Database name                              │
 │  REDIS_URL         │  redis://redis:6379/0     │  Redis URL for broker/backend + pub/sub     │
 │  DEFAULT_MODEL     │  gpt-4.1                  │  Default model for new workflows            │
 │  DEFAULT_MAX_TURNS │  5                        │  Default max tool-call turns per workflow    │
 │  SESSION_TIMEOUT   │  300                      │  SDK session timeout in seconds             │
 │  GITHUB_TOKEN      │  —                        │  Server-level GitHub PAT                    │
 │  NOTION_TOKEN      │  —                        │  Notion integration token                   │
 │  SLACK_BOT_TOKEN   │  —                        │  Slack bot token                            │
 │  DD_API_KEY        │  —                        │  Datadog API key                            │
 │  DD_APP_KEY        │  —                        │  Datadog App key                            │
 │  DD_SITE           │  datadoghq.com            │  Datadog site                               │
 │  ATLASSIAN_API_TOK │  —                        │  Atlassian API token                        │
 │  ATLASSIAN_EMAIL   │  —                        │  Atlassian account email                    │
 │  ATLASSIAN_URL     │  —                        │  Atlassian site URL                         │
 └────────────────────┴───────────────────────────┴─────────────────────────────────────────────┘
```

---

## ✅ Verifying the setup

```bash
# ► Health check
curl http://localhost:8000/health

# ► Create a simple agent
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "system_prompt": "You are a helpful assistant."}'

# ► Check the dashboard
open http://localhost:8000/dashboard
```

---

## 🔧 Troubleshooting

```
 ┌─────────────────────────────────────┬─────────────────────────────────────────────────────────┐
 │  ░░ PROBLEM                         │  ░░ SOLUTION                                            │
 ├─────────────────────────────────────┼─────────────────────────────────────────────────────────┤
 │  Connection refused on port 8000    │  Ensure uvicorn or the app container is running          │
 │  Connection refused on Redis/Mongo  │  Start the infrastructure containers or native services  │
 │  Workers not picking up tasks       │  Verify REDIS_URL matches between API and worker         │
 │  MCP server fails to start          │  Ensure Node.js 22+ is installed (npx needs it)         │
 │  copilot scope errors               │  Regenerate your GitHub PAT with copilot scope enabled  │
 └─────────────────────────────────────┴─────────────────────────────────────────────────────────┘
```

---

<p align="center">⬛⬜⬛ <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⬛⬜⬛</p>
