# Local Setup

Run TBD Agents on your development machine — Docker or bare metal.

---

## Prerequisites

| Requirement | Why |
|---|---|
| Docker & Docker Compose | Fastest path — runs everything in one command |
| GitHub PAT (`copilot` scope) | Authenticates agent sessions against the Copilot SDK |
| Copilot subscription | Individual, Business, or Enterprise — premium request quota |
| Node.js 22+ | Required by npx-based MCP servers (included in Docker image) |
| Python 3.12+ | Only needed for bare-metal development |
| Flutter 3.32+ with web support | Needed only when you are changing `frontend/` locally |

[Create a GitHub PAT →](https://github.com/settings/tokens)

---

## Option 1 — Docker Compose (recommended)

=== "MongoDB (default)"

    ```bash
    git clone https://github.com/naaico-tech/tbd-agents.git && cd tbd-agents
    cp .env.example .env
    # Edit .env and fill in at least GITHUB_TOKEN
    docker compose up --build
    ```

    | Service | Port | Description |
    |---|---|---|
    | `app` | 8000 | FastAPI API + Flutter dashboard |
    | `worker` | — | Celery worker (4 concurrent slots) |
    | `redis` | 6379 | Task broker + event bus |
    | `mongodb` | 27017 | Document store |
    | `qdrant` | 6333 | Vector store |

=== "PostgreSQL"

    Add the following to your `.env`, then start:

    ```env
    COMPOSE_PROFILES=pgvector
    DB_BACKEND=postgres
    VECTOR_STORE_BACKEND=pgvector
    POSTGRES_URI=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents
    ```

    ```bash
    docker compose up --build
    # Apply schema on first run
    docker compose exec app alembic upgrade head
    ```

    | Service | Port | Description |
    |---|---|---|
    | `app` | 8000 | FastAPI API + Flutter dashboard |
    | `worker` | — | Celery worker (4 concurrent slots) |
    | `redis` | 6379 | Task broker + event bus |
    | `pgvector` | 5432 | PostgreSQL 16 with pgvector (replaces MongoDB + Qdrant) |

    !!! note
        The `pgvector` profile starts a single PostgreSQL container that handles both document storage and vector search. MongoDB and Qdrant are not started.

### Scaling workers

```bash
# Run 3 worker containers instead of 1
docker compose up --build --scale worker=3
```

Each worker defaults to `--concurrency=4`, so 3 containers = 12 concurrent agent executions.

The application image builds the Flutter web bundle during `docker compose up --build`, serves it from FastAPI at `/dashboard-new-ui`, and keeps the legacy dashboard available at `/dashboard` (with `/dashboard-legacy` as a compatibility alias).

---

## Option 2 — Bare Metal

### Step 1 — Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Step 2 — Start infrastructure

=== "MongoDB"

    ```bash
    # MongoDB
    docker run -d --name mongo -p 27017:27017 mongo:7

    # Qdrant
    docker run -d --name qdrant -p 6333:6333 qdrant/qdrant

    # Redis
    docker run -d --name redis -p 6379:6379 redis:7-alpine
    ```

    Or install natively via `brew install mongodb-community redis` (macOS).

=== "PostgreSQL"

    ```bash
    # PostgreSQL with pgvector
    docker run -d --name pgvector \
      -p 5432:5432 \
      -e POSTGRES_PASSWORD=postgres \
      -e POSTGRES_DB=tbd_agents \
      pgvector/pgvector:pg16

    # Redis
    docker run -d --name redis -p 6379:6379 redis:7-alpine
    ```

    Or install natively: `brew install postgresql` and enable the pgvector extension:

    ```bash
    psql -U postgres -d tbd_agents -c "CREATE EXTENSION IF NOT EXISTS vector;"
    ```

### Step 3 — Set environment variables

=== "MongoDB"

    ```bash
    export MONGO_URI=mongodb://localhost:27017
    export REDIS_URL=redis://localhost:6379/0
    export GITHUB_TOKEN="ghp_your_token_here"
    ```

=== "PostgreSQL"

    ```bash
    export DB_BACKEND=postgres
    export POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents
    export VECTOR_STORE_BACKEND=pgvector
    export PGVECTOR_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents
    export REDIS_URL=redis://localhost:6379/0
    export GITHUB_TOKEN="ghp_your_token_here"
    ```

Or create a `.env` file from the template — Pydantic Settings loads it automatically:

```bash
cp .env.example .env
```

### Step 4 — Apply schema migrations (PostgreSQL only)

```bash
DB_BACKEND=postgres alembic upgrade head
```

This is a no-op when `DB_BACKEND=mongo`.

### Step 5 — Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

### Optional — rebuild the Flutter dashboard locally

If you are changing files under `frontend/`, build the web bundle that FastAPI serves:

```bash
cd frontend
flutter config --enable-web
flutter pub get
flutter analyze
flutter test
flutter build web --release --base-href /dashboard-new-ui/
cd ..
```

### Step 6 — Start a Celery worker

In a separate terminal (same virtualenv):

```bash
celery -A app.celery_app worker --loglevel=info --concurrency=4
```

---

## Verifying the setup

```bash
# Health check
curl http://localhost:8000/health

# Create a simple agent
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "system_prompt": "You are a helpful assistant."}'

# Check the Flutter dashboard
open http://localhost:8000/dashboard-new-ui

# Check the legacy dashboard
open http://localhost:8000/dashboard
```

---

## Running Tests

```bash
# Unit tests (MongoDB-agnostic, no external services needed)
python -m pytest tests/ --ignore=tests/integration --ignore=tests/integration_postgres -v

# MongoDB integration tests (requires running MongoDB + Redis)
python -m pytest tests/integration/ -v

# PostgreSQL integration tests (requires running PostgreSQL)
DB_BACKEND=postgres \
  POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents_integration_test \
  python -m pytest tests/integration_postgres/ -v

# Lint check
ruff check app/ tests/

# Auto-format
ruff format app/ tests/

# Frontend checks (when touching frontend/)
cd frontend
flutter analyze
flutter test
flutter build web --release --base-href /dashboard-new-ui/
```

!!! note
    Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — all async test functions are picked up automatically.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Connection refused on port 8000 | Ensure uvicorn or the app container is running |
| Connection refused on Redis/Mongo | Start infrastructure containers or native services |
| Workers not picking up tasks | Verify `REDIS_URL` matches between API and worker |
| MCP server fails to start | Ensure Node.js 22+ is installed (npx needs it) |
| `copilot` scope errors | Regenerate your GitHub PAT with copilot scope enabled |
| Token encryption errors | Set `TOKEN_ENCRYPTION_KEY` in .env (see .env.example) |
| `relation "agents" does not exist` | Run `alembic upgrade head` after setting `DB_BACKEND=postgres` |
| App still reads MongoDB when using `DB_BACKEND=postgres` | Restart the app and worker after changing `.env` |
