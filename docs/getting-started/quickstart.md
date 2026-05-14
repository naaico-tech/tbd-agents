# Quick Start

Get TBD Agents running in under 5 minutes with Docker Compose.

TBD Agents supports two database backends. Choose the one that fits your stack:

| Backend | Storage | Vector search | Best for |
|---|---|---|---|
| **MongoDB** *(default)* | MongoDB 7 | Qdrant | Existing Mongo users, fastest start |
| **PostgreSQL** | PostgreSQL 16 (JSONB) | pgvector | New deployments, single-DB ops, Kubernetes |

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
```

Open `.env` and set at minimum:

```env
GITHUB_TOKEN=ghp_your_token_here
```

---

## 2. Start the stack

=== "MongoDB (default)"

    No extra configuration needed — MongoDB is the default backend.

    ```bash
    docker compose up --build
    ```

    Services started:

    | Service | Port | Description |
    |---|---|---|
    | `app` | 8000 | FastAPI API + dashboards |
    | `worker` | — | Celery worker (4 concurrent slots) |
    | `redis` | 6379 | Task broker + event bus |
    | `mongodb` | 27017 | Document store |
    | `qdrant` | 6333 | Vector store |

    !!! tip "Choose your vector store"
        Qdrant starts by default. To start without any vector store (no semantic memory), simply omit `COMPOSE_PROFILES` from `.env`.

=== "PostgreSQL"

    Add four lines to your `.env`:

    ```env
    COMPOSE_PROFILES=pgvector
    DB_BACKEND=postgres
    VECTOR_STORE_BACKEND=pgvector
    POSTGRES_URI=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents
    ```

    Then start:

    ```bash
    docker compose up --build
    ```

    Services started:

    | Service | Port | Description |
    |---|---|---|
    | `app` | 8000 | FastAPI API + dashboards |
    | `worker` | — | Celery worker (4 concurrent slots) |
    | `redis` | 6379 | Task broker + event bus |
    | `pgvector` | 5432 | PostgreSQL 16 with pgvector extension |

    !!! note "Single database, no MongoDB, no Qdrant"
        The `pgvector` profile starts **one** container that handles both document storage and vector search. MongoDB and Qdrant are not started.

    Apply database schema migrations on first start:

    ```bash
    docker compose exec app alembic upgrade head
    ```

!!! tip "Access points"
    - **Flutter UI** — [http://localhost:8000/dashboard-new-ui](http://localhost:8000/dashboard-new-ui)
    - **Legacy UI** — [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
    - **Swagger UI** — [http://localhost:8000/docs](http://localhost:8000/docs)
    - **API base** — [http://localhost:8000/api](http://localhost:8000/api)

---

## 3. Verify the stack is healthy

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

## 4. Create an agent

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

Copy the `id` field from the response — you will need it in the next step.

---

## 5. Create a workflow and send a prompt

```bash
# Create workflow (replace <AGENT_ID> with the id from step 4)
WORKFLOW=$(curl -s -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "max_turns": 10,
    "output_format": "markdown"
  }')

WORKFLOW_ID=$(echo "$WORKFLOW" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

# Send a prompt
curl -X POST "http://localhost:8000/api/workflows/$WORKFLOW_ID/prompt" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Review the code in the main module for security issues."}'
```

---

## 6. Stream results in real-time

```bash
curl -N "http://localhost:8000/api/workflows/$WORKFLOW_ID/stream"
```

Server-sent events will stream the agent's response as it is generated.

---

## What's next?

- [Local Setup](local-setup.md) — bare-metal development, environment variables, troubleshooting
- [Configuration](configuration.md) — full reference for all environment variables
- [PostgreSQL Backend](../guide/postgres-backend.md) — migrations, schema design, backup/restore
- [pgvector Setup](../guide/pgvector.md) — vector store tuning, indexing strategy, observability
- [Guide](../guide/index.md) — agents, MCP tools, skills, streaming, and more
