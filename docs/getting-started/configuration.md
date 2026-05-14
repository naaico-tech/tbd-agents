# Configuration

Configuration is read from environment variables. Pydantic Settings also loads `.env` automatically.

## Core Runtime

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_MODEL` | `gpt-4.1` | Default model when none is selected |
| `DEFAULT_MAX_TURNS` | `5` | Default workflow max turns |
| `SESSION_TIMEOUT` | `600` | SDK/session timeout in seconds |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker/backend and event bus |
| `API_BASE_URL` | `http://app:8000` | Internal API URL used by memory MCP subprocesses |
| `GITHUB_TOKEN` | unset | Optional server-level GitHub token; per-request Bearer/provider tokens may take priority |
| `TOKEN_ENCRYPTION_KEY` | unset | Fernet key for encrypted token store |
| `ANTHROPIC_GATEWAY_MAX_TOKENS` | `8192` | Max output tokens for Anthropic gateway path |

## Document Store

| Variable | Default | Description |
|---|---|---|
| `DB_BACKEND` | `mongo` | `mongo` or `postgres` |
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB URI |
| `MONGO_DB_NAME` | `copilot_agent_hub` | MongoDB database name |
| `POSTGRES_URI` | `postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents` | Async PostgreSQL URI |
| `POSTGRES_DB_NAME` | `tbd_agents` | PostgreSQL database name |

## Compose Profiles and Vector Store

`.env.example` actively defaults to `COMPOSE_PROFILES=qdrant` and `DB_BACKEND=mongo`. If `COMPOSE_PROFILES` is omitted entirely, Docker Compose does not start a profiled vector/document database; use that only when external services are configured.

| Variable | Default | Description |
|---|---|---|
| `COMPOSE_PROFILES` | `qdrant` in `.env.example` | `qdrant` for MongoDB + Qdrant, `pgvector` for PostgreSQL-only stack |
| `VECTOR_STORE_BACKEND` | `qdrant` | `qdrant` or `pgvector` |
| `QDRANT_URL` | unset in code; `.env.example` uses `http://localhost:6333` | Qdrant URL (`http://qdrant:6333` inside Docker) |
| `QDRANT_API_KEY` | unset | Optional Qdrant API key |
| `PGVECTOR_DSN` | defaults to `POSTGRES_URI` when unset | Pgvector DSN |
| `PGVECTOR_TABLE_PREFIX` | `vs` | Vector collection table prefix |

All-PostgreSQL Docker stack:

```env
COMPOSE_PROFILES=pgvector
DB_BACKEND=postgres
VECTOR_STORE_BACKEND=pgvector
POSTGRES_URI=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents
# Optional; defaults to POSTGRES_URI when omitted
PGVECTOR_DSN=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents
```

Run `docker compose exec app alembic upgrade head` on first PostgreSQL startup.

## Memory, Embeddings, and Prompt Budgets

| Variable | Default | Description |
|---|---|---|
| `STM_MAX_ENTRIES` | `20` | Recent memories cached per agent in Redis |
| `LTM_MAX_ENTRIES` | `200` | Durable memories per agent; `0` = unlimited |
| `EMBEDDINGS_ENABLED` | `true` | Enable semantic memory/knowledge retrieval |
| `EMBEDDINGS_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model |
| `EMBEDDINGS_DIM` | `384` | Vector dimension used for collection creation |
| `MEMORY_RETRIEVAL_TOP_K` | `8` | Semantic memory retrieval limit |
| `KNOWLEDGE_RETRIEVAL_TOP_K` | `8` | Semantic knowledge retrieval limit |
| `KNOWLEDGE_CHUNK_CHARS` | `1200` | Chunk size for knowledge ingestion |
| `KNOWLEDGE_CHUNK_OVERLAP_CHARS` | `150` | Chunk overlap |
| `PROMPT_CONTEXT_CHAR_BUDGET` | `24000` | Total injected context character budget |
| `PROMPT_SKILLS_CHAR_BUDGET` | `6000` | Skills budget |
| `PROMPT_KNOWLEDGE_CHAR_BUDGET` | `12000` | Knowledge budget |
| `PROMPT_MEMORY_CHAR_BUDGET` | `4000` | Memory budget |
| `PROMPT_CONTEXT_ITEM_CHAR_LIMIT` | `1200` | Per-item context limit |
| `PROMPT_CONTEXT_MAX_ITEMS` | `12` | Max context items |

## Compaction and Tool Context

| Variable | Default | Description |
|---|---|---|
| `COMPACTION_ENABLED` | `true` | Enable conversation compaction |
| `COMPACTION_TOKEN_THRESHOLD_PCT` | `0.75` | Start compaction threshold |
| `COMPACTION_KEEP_RECENT_TURNS` | `6` | Recent turns retained around compaction |
| `COMPACTION_SUMMARY_MAX_CHARS` | `1500` | Max compaction summary size |
| `TOOL_RESULT_CLEARING_ENABLED` | `true` | Clear old tool results from context |
| `TOOL_RESULT_CLEARING_KEEP_RECENT` | `4` | Recent tool results retained |
| `TOOL_RESULT_CONTEXT_MAX_CHARS` | `4000` | Max chars for tool result context |
| `TOOL_DEFINITION_DESCRIPTION_MAX_CHARS` | `240` | Max chars for tool descriptions |

## Plugin and Observability Settings

| Variable | Default | Description |
|---|---|---|
| `PLUGINS_DIR` | `app/plugins` | Plugin module directory |
| `PLUGINS_CONFIG` | `app/plugins.yaml` | Plugin registry file |
| `OTEL_ENDPOINT` | `http://otel-collector:4317` | gRPC OpenTelemetry endpoint |
| `OTEL_HTTP_ENDPOINT` | `http://otel-collector:4318` | HTTP OpenTelemetry endpoint |
| `OTEL_SERVICE_NAME` | `tbd-agents` | Service name |
