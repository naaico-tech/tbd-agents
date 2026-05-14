# Configuration

All configuration is managed through environment variables. Pydantic Settings loads them from `.env` automatically.

---

## Core Settings

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `copilot_agent_hub` | Database name |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL for broker/backend + pub/sub |
| `DEFAULT_MODEL` | `gpt-4.1` | Default model for new workflows |
| `DEFAULT_MAX_TURNS` | `5` | Default max tool-call turns per workflow |
| `SESSION_TIMEOUT` | `300` | SDK session timeout in seconds |

---

## Authentication Tokens

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | Server-level GitHub PAT (requires `copilot` scope) |
| `TOKEN_ENCRYPTION_KEY` | — | Fernet key for encrypting stored tokens |

!!! warning
    `GITHUB_TOKEN` is required. Without it, agent sessions cannot authenticate against the Copilot SDK.

---

## Database Backend

TBD Agents supports two document store backends. Set `DB_BACKEND` to select between them.

| Variable | Default | Description |
|---|---|---|
| `DB_BACKEND` | `mongo` | Document store backend: `mongo` or `postgres` |

### MongoDB backend (default)

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `copilot_agent_hub` | MongoDB database name |

No additional variables are needed when using the default MongoDB backend.

### PostgreSQL backend

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_URI` | `postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents` | asyncpg-compatible PostgreSQL connection string |
| `POSTGRES_DB_NAME` | `tbd_agents` | PostgreSQL database name |

!!! important
    `DB_BACKEND=postgres` and `COMPOSE_PROFILES=pgvector` must be set together.
    Using one without the other mismatches the running containers with the application data layer.

---

## Vector Store Backend

| Variable | Default | Description |
|---|---|---|
| `VECTOR_STORE_BACKEND` | `qdrant` | Active vector store: `qdrant` or `pgvector` |
| `COMPOSE_PROFILES` | _(none)_ | Docker Compose profile: `qdrant` or `pgvector` |

### Qdrant (default)

| Variable | Default | Description |
|---|---|---|
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant service URL |

### pgvector

| Variable | Default | Description |
|---|---|---|
| `PGVECTOR_DSN` | — | asyncpg DSN for the pgvector database (required when `VECTOR_STORE_BACKEND=pgvector`) |
| `PGVECTOR_TABLE_PREFIX` | `vs` | Prefix for all vector collection tables |
| `PGVECTOR_USER` | `postgres` | Postgres username (Docker service only) |
| `PGVECTOR_PASSWORD` | `postgres` | Postgres password (Docker service only) |
| `PGVECTOR_DB` | `tbd_agents` | Database name (Docker service only) |
| `PGVECTOR_PORT` | `5432` | Host port mapped to the container (Docker service only) |

---

## Integration Tokens

These are optional and only needed if you use the corresponding MCP servers:

| Variable | Default | Description |
|---|---|---|
| `NOTION_TOKEN` | — | Notion integration token |
| `SLACK_BOT_TOKEN` | — | Slack bot token |
| `DD_API_KEY` | — | Datadog API key |
| `DD_APP_KEY` | — | Datadog App key |
| `DD_SITE` | `datadoghq.com` | Datadog site |
| `ATLASSIAN_API_TOKEN` | — | Atlassian API token |
| `ATLASSIAN_EMAIL` | — | Atlassian account email |
| `ATLASSIAN_URL` | — | Atlassian site URL |

---

## Setting Up

=== "MongoDB (Docker Compose)"

    ```bash
    cp .env.example .env
    # Set GITHUB_TOKEN and TOKEN_ENCRYPTION_KEY at minimum
    docker compose up --build
    ```

    Minimal `.env`:

    ```env
    GITHUB_TOKEN=ghp_your_token_here
    TOKEN_ENCRYPTION_KEY=<fernet_key>
    ```

=== "PostgreSQL (Docker Compose)"

    ```bash
    cp .env.example .env
    # Edit .env — add the four PostgreSQL lines below
    docker compose up --build
    docker compose exec app alembic upgrade head
    ```

    Required additions to `.env`:

    ```env
    GITHUB_TOKEN=ghp_your_token_here
    TOKEN_ENCRYPTION_KEY=<fernet_key>
    COMPOSE_PROFILES=pgvector
    DB_BACKEND=postgres
    VECTOR_STORE_BACKEND=pgvector
    POSTGRES_URI=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents
    ```

=== "MongoDB (Bare Metal)"

    ```bash
    export MONGO_URI=mongodb://localhost:27017
    export REDIS_URL=redis://localhost:6379/0
    export GITHUB_TOKEN="ghp_your_token_here"
    ```

    Or use a `.env` file — Pydantic Settings loads it automatically.

=== "PostgreSQL (Bare Metal)"

    ```bash
    export DB_BACKEND=postgres
    export POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents
    export VECTOR_STORE_BACKEND=pgvector
    export PGVECTOR_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents
    export REDIS_URL=redis://localhost:6379/0
    export GITHUB_TOKEN="ghp_your_token_here"

    # Apply schema migrations
    alembic upgrade head
    ```

!!! tip "Generating a TOKEN_ENCRYPTION_KEY"
    ```bash
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```
