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
| `SESSION_TIMEOUT` | `600` | SDK session timeout in seconds |

---

## Authentication Tokens

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | Optional server-level GitHub PAT (per-request or provider tokens can take priority) |
| `TOKEN_ENCRYPTION_KEY` | — | Fernet key for encrypting stored tokens |

!!! note
    `GITHUB_TOKEN` is still useful for local development and default Copilot SDK authentication. Deployments can also use per-request `Authorization: Bearer ...` tokens or provider-backed credentials where supported.

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
| `COMPOSE_PROFILES` | `qdrant` in `.env.example` | Docker Compose profile: `qdrant` or `pgvector`; empty means no vector-store service |

### Qdrant (default)

| Variable | Default | Description |
|---|---|---|
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant service URL |
| `QDRANT_API_KEY` | — | Optional Qdrant API key |

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

## Prompt, Memory, and Embedding Settings

| Variable | Default | Description |
|---|---|---|
| `STM_MAX_ENTRIES` | `20` | Recent memories per agent cached in Redis |
| `LTM_MAX_ENTRIES` | `200` | Long-term memories per agent (`0` = unlimited) |
| `PROMPT_CONTEXT_CHAR_BUDGET` | `24000` | Approximate total prompt context budget |
| `PROMPT_SKILLS_CHAR_BUDGET` | `6000` | Skills context budget |
| `PROMPT_KNOWLEDGE_CHAR_BUDGET` | `12000` | Knowledge context budget |
| `PROMPT_MEMORY_CHAR_BUDGET` | `4000` | Memory context budget |
| `PROMPT_CONTEXT_ITEM_CHAR_LIMIT` | `1200` | Max chars per injected context item |
| `PROMPT_CONTEXT_MAX_ITEMS` | `12` | Max context items injected |
| `EMBEDDINGS_ENABLED` | `true` | Enable semantic memory and knowledge retrieval |
| `EMBEDDINGS_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model name |
| `EMBEDDINGS_DIM` | `384` | Embedding dimension used for vector collections |
| `MEMORY_RETRIEVAL_TOP_K` | `8` | Semantic memory matches |
| `KNOWLEDGE_RETRIEVAL_TOP_K` | `8` | Semantic knowledge matches |
| `KNOWLEDGE_CHUNK_CHARS` | `1200` | Knowledge chunk size |
| `KNOWLEDGE_CHUNK_OVERLAP_CHARS` | `150` | Overlap between chunks |

## Compaction and Tool Result Settings

| Variable | Default | Description |
|---|---|---|
| `COMPACTION_ENABLED` | `true` | Enable conversation compaction |
| `COMPACTION_TOKEN_THRESHOLD_PCT` | `0.75` | Compact near this context-window threshold |
| `COMPACTION_KEEP_RECENT_TURNS` | `6` | Recent turns preserved during compaction |
| `COMPACTION_SUMMARY_MAX_CHARS` | `1500` | Max compaction summary size |
| `TOOL_RESULT_CLEARING_ENABLED` | `true` | Trim older tool results from context |
| `TOOL_RESULT_CLEARING_KEEP_RECENT` | `4` | Recent tool results to keep |
| `TOOL_RESULT_CONTEXT_MAX_CHARS` | `4000` | Max retained chars per tool-result context |
| `TOOL_DEFINITION_DESCRIPTION_MAX_CHARS` | `240` | Max tool description length injected into prompts |

## Runtime Integration Settings

| Variable | Default | Description |
|---|---|---|
| `API_BASE_URL` | `http://app:8000` | Internal API base URL used by subprocess helpers |
| `PLUGINS_DIR` | `app/plugins` | Plugin module directory |
| `PLUGINS_CONFIG` | `app/plugins.yaml` | Plugin configuration file |
| `OTEL_ENDPOINT` | `http://otel-collector:4317` | OpenTelemetry gRPC collector endpoint |
| `OTEL_HTTP_ENDPOINT` | `http://otel-collector:4318` | OpenTelemetry HTTP collector endpoint |
| `OTEL_SERVICE_NAME` | `tbd-agents` | OpenTelemetry service name |
| `ANTHROPIC_GATEWAY_MAX_TOKENS` | `8192` | Max output tokens for Anthropic gateway/messages path |

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
