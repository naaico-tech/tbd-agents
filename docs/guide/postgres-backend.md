# PostgreSQL Backend Guide

TBD Agents supports a fully-PostgreSQL deployment stack via the `pgvector` profile.
This guide covers everything you need to know to run, configure, migrate to, and
operate the PostgreSQL backend.

---

## Overview

By default TBD Agents uses **MongoDB** as its document store (the `qdrant` profile).
The `pgvector` profile replaces MongoDB with **PostgreSQL 16**, using JSONB columns
to store the same document structures — and it reuses that **same** PostgreSQL instance
for vector storage via the [pgvector](https://github.com/pgvector/pgvector) extension.

### Why choose the PostgreSQL backend?

| Benefit | Detail |
|---|---|
| **Single database service** | One PostgreSQL container handles both document storage and vector search — no MongoDB to run alongside Qdrant |
| **Unified backup / restore** | A single `pg_dump` snapshot captures all agent data _and_ all vector embeddings |
| **Familiar ops tooling** | Standard PostgreSQL tooling (psql, pgAdmin, pg_dump, Alembic) works out of the box |
| **Kubernetes-friendly** | One StatefulSet / PVC instead of two separate ones |
| **JSONB flexibility** | Same schemaless document semantics as MongoDB with full SQL query power on top |
| **pgvector + data in one place** | Vector search and relational queries share the same ACID transaction boundary |

---

## Profile Comparison

| Feature | `qdrant` profile | `pgvector` profile |
|---|---|---|
| **Document store** | MongoDB 7 | PostgreSQL 16 (JSONB) |
| **Vector store** | Qdrant | pgvector extension |
| **Services needed** | 2 (`mongodb` + `qdrant`) | 1 (`pgvector` with pgvector) |
| **Data backup** | `mongodump` + Qdrant snapshot | `pg_dump` only |
| **Migrations** | Beanie (schema-less) | Alembic |
| **Recommended for** | Existing MongoDB users | New deployments, Kubernetes, simplicity |

---

## Quick Start — all-PostgreSQL stack

### 1. Configure `.env`

```env
COMPOSE_PROFILES=pgvector
VECTOR_STORE_BACKEND=pgvector
DB_BACKEND=postgres
POSTGRES_URI=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents
```

### 2. Start services

```bash
docker compose up -d
```

This starts a single `pgvector` container with the pgvector extension pre-installed.
No MongoDB, no Qdrant.

### 3. Apply database migrations

```bash
docker compose exec app alembic upgrade head
```

### 4. Verify

```bash
docker compose ps          # pgvector should be Up
docker compose exec app alembic current   # should show head revision
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DB_BACKEND` | `mongo` | Document store backend: `mongo` or `postgres` |
| `POSTGRES_URI` | `postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents` | Async-compatible PostgreSQL connection string (uses `asyncpg` driver) |
| `POSTGRES_DB_NAME` | `tbd_agents` | PostgreSQL database name |
| `COMPOSE_PROFILES` | `qdrant` in `.env.example` | Docker Compose profile: `qdrant` or `pgvector`; empty starts no vector-store service |
| `VECTOR_STORE_BACKEND` | `qdrant` | Vector store backend: `qdrant` or `pgvector` — must match `COMPOSE_PROFILES` |

> **Important:** `DB_BACKEND=postgres` and `COMPOSE_PROFILES=pgvector` must always be set
> together. Using one without the other will result in a mismatch between the running
> containers and the application's data layer.

---

## Schema Design

The PostgreSQL backend maps each logical MongoDB collection to a dedicated table with
**proper typed columns** — each field is represented as its native SQL type (`TEXT`,
`INTEGER`, `BOOLEAN`, `TIMESTAMPTZ`, `TEXT[]`, `JSONB`, etc.) rather than a generic
`data JSONB` blob. This gives you full SQL query power, type safety, and the ability
to add column-level indexes where needed.

```sql
-- Example: the agents table (fully typed)
CREATE TABLE agents (
    id                  TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name                TEXT        NOT NULL,
    description         TEXT        NOT NULL DEFAULT '',
    system_prompt       TEXT        NOT NULL DEFAULT 'You are a helpful assistant.',
    model               TEXT,
    mcp_server_ids      TEXT[]      NOT NULL DEFAULT '{}',
    mcp_server_tags     TEXT[]      NOT NULL DEFAULT '{}',
    tool_definitions    JSONB       NOT NULL DEFAULT '[]',
    knowledge_source_ids TEXT[]     NOT NULL DEFAULT '{}',
    knowledge_tags      TEXT[]      NOT NULL DEFAULT '{}',
    builtin_tools       TEXT[]      NOT NULL DEFAULT '{}',
    custom_tool_ids     TEXT[]      NOT NULL DEFAULT '{}',
    provider_id         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

JSONB is retained only for genuinely schemaless or nested payloads (e.g.
`tool_definitions`, `connection_config`, `messages`, `usage`). Array fields use the
native PostgreSQL `TEXT[]` type. Where appropriate, tables carry targeted B-tree
indexes (e.g. `idx_chat_sessions_agent_id`) instead of a catch-all GIN index.

### All 15 tables

| Table | Key typed columns |
|---|---|
| `agents` | `name`, `model`, `mcp_server_ids TEXT[]`, `tool_definitions JSONB` |
| `chat_sessions` | `agent_id`, `github_user`, `title`, `message_count INTEGER` |
| `chat_messages` | `session_id`, `role`, `content`, `usage JSONB` |
| `memories` | `agent_id`, `scope`, `key`, `value`, `embedding DOUBLE PRECISION[]`, `metadata JSONB` |
| `skills` | `name`, `instructions`, `tags TEXT[]` |
| `tokens` | `name UNIQUE`, `encrypted_value`, `created_by` |
| `providers` | `name UNIQUE`, `provider_type`, `api_key_token_name`, `auth_type`, `base_url` |
| `knowledge_items` | `source_id`, `content_type`, `text_content`, `file_name`, `file_size INTEGER` |
| `knowledge_sources` | `name`, `source_type`, `connection_config JSONB`, `status` |
| `custom_tools` | `name`, `source_code`, `parameters_schema JSONB`, `is_enabled BOOLEAN` |
| `guardrails` | `name`, `guardrail_type`, `enabled BOOLEAN`, `prompt_config JSONB` |
| `workflows` | `agent_id`, `status`, `max_turns INTEGER`, `messages JSONB`, `logs JSONB` |
| `task_executions` | `workflow_id`, `status`, `celery_task_id`, `tool_calls INTEGER`, `usage JSONB` |
| `scheduled_agents` | `workflow_id`, `interval_value INTEGER`, `interval_unit`, `enabled BOOLEAN` |
| `mcp_servers` | `name`, `transport_type`, `connection_config JSONB`, `allowed_tools TEXT[]`, `status` |

---

## Running Database Migrations (Alembic)

TBD Agents uses [Alembic](https://alembic.sqlalchemy.org/) to manage the PostgreSQL
schema. Migrations are a no-op when `DB_BACKEND=mongo`.

```bash
# Apply all pending migrations (create/update tables)
docker compose exec app alembic upgrade head

# Or run locally with uv (DB must be reachable)
DB_BACKEND=postgres uv run alembic upgrade head

# Check which revision is currently applied
alembic current

# Show the full migration history
alembic history --verbose

# Roll back one revision
alembic downgrade -1

# Generate a new migration after changing a model
# Note: autogenerate is not configured (target_metadata = None in alembic/env.py).
# Write the migration manually after creating the file.
alembic revision -m "describe_your_change"
```

> **Tip:** Migrations are idempotent — running `upgrade head` on an already-migrated
> database is safe and produces no changes.

---

## Data Migration from MongoDB to PostgreSQL

If you have an existing deployment running the `qdrant` profile and want to switch
to `pgvector`, use the provided migration script.

### Prerequisites

- Both MongoDB and PostgreSQL must be running and reachable.
- PostgreSQL tables must already exist (`alembic upgrade head` first).

### Run the migration

```bash
# Connection info is read from environment variables
# (MONGO_URI, MONGO_DB_NAME, POSTGRES_URI) with sensible defaults.
MONGO_URI=mongodb://localhost:27017 \
MONGO_DB_NAME=copilot_agent_hub \
POSTGRES_URI=postgresql://postgres:postgres@localhost:5432/tbd_agents \
python scripts/migrate_mongo_to_postgres.py \
  [--dry-run]             # preview without writing any data
  [--collection NAME]     # migrate one specific collection (default: all 15)
  [--batch-size N]        # documents per INSERT batch (default: 500)
  [--verbose]             # print per-batch progress
```

!!! warning "MongoDB database name"
    The running application defaults to `MONGO_DB_NAME=copilot_agent_hub`, while
    the migration helper's historical default is `tbd_agents`. Set
    `MONGO_DB_NAME=copilot_agent_hub` explicitly when migrating data from the
    default Docker/app deployment, otherwise you may migrate an empty database.

| Flag | Description |
|---|---|
| `--dry-run` | Print what would be migrated without touching PostgreSQL |
| `--collection NAME` | Migrate only the named collection (default: all 15) |
| `--batch-size N` | Number of documents per INSERT batch (default: 500) |
| `--verbose` | Print progress after each batch |

### Verify the migration

```bash
# Set env vars first (script reads them automatically):
#   MONGO_URI, MONGO_DB_NAME, POSTGRES_URI
python scripts/verify_migration.py \
  [--collection agents]    # verify a single named collection (default: all 15)
```

The verification script compares document counts per collection and reports any
discrepancies.

### Switch over

Once verification passes, update `.env`:

```env
COMPOSE_PROFILES=pgvector
DB_BACKEND=postgres
```

Then restart the application:

```bash
docker compose down && docker compose up -d
```

---

## Observability

### Table sizes and row counts

```sql
SELECT
    relname                                         AS table,
    n_live_tup                                      AS rows,
    pg_size_pretty(pg_total_relation_size(relid))   AS total_size
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

### Inspect recent agents

```sql
-- Most recently created agents
SELECT id, name, model, created_at
FROM agents
ORDER BY created_at DESC
LIMIT 10;
```

### Query by column value

```sql
-- All agents using a specific model
SELECT id, name, model
FROM agents
WHERE model = 'claude-opus-4-5';
```

### Aggregate across typed fields

```sql
-- Memory count per agent
SELECT
    agent_id,
    COUNT(*) AS memories
FROM memories
GROUP BY agent_id
ORDER BY memories DESC;
```

### Index usage health check

```sql
-- Confirm B-tree indexes are being used
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE indexrelname LIKE 'idx_%'
ORDER BY idx_scan DESC;
```

---

## Backup & Restore

Because vectors and documents live in the same PostgreSQL instance, a single
`pg_dump` covers your entire dataset.

### Backup

```bash
# Via Docker Compose
docker compose exec pgvector \
  pg_dump -U postgres tbd_agents > backup.sql

# Or with a timestamp
docker compose exec pgvector \
  pg_dump -U postgres -F custom tbd_agents \
  -f /tmp/tbd_$(date +%Y%m%d_%H%M%S).dump
```

### Restore

```bash
# Plain SQL dump
docker compose exec -i pgvector \
  psql -U postgres tbd_agents < backup.sql

# Custom-format dump (parallel restore, faster for large databases)
docker compose exec pgvector \
  pg_restore -U postgres -d tbd_agents -j 4 /tmp/tbd_backup.dump
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `connection refused` on startup | PostgreSQL not running or wrong profile active | Verify `COMPOSE_PROFILES=pgvector` in `.env`; run `docker compose ps` to confirm the `pgvector` container is `Up` |
| `relation "agents" does not exist` | Tables have not been created | Run `alembic upgrade head` inside the app container |
| `column "X" does not exist` | asyncpg type mismatch or column name wrong | Confirm the column name matches the typed schema; ensure `json_serializer` / `json_deserializer` are set in the SQLAlchemy engine config (see `app/db.py`) |
| App still reads/writes MongoDB | `DB_BACKEND` not set to `postgres` | Add `DB_BACKEND=postgres` to `.env` and restart the app |
| Slow queries on foreign-key-like columns | Missing B-tree index | Run `CREATE INDEX CONCURRENTLY idx_<table>_<col> ON <table> (<col>);` — no downtime required |
| pgvector extension not found | PostgreSQL image without pgvector | Use the `pgvector/pgvector:pg16` image (configured automatically by the `pgvector` compose profile) |
| Migration script fails with permission errors | PostgreSQL user lacks `CREATE` privilege | Grant superuser or `CREATE ON DATABASE` to the connection user |

---

## See Also

- [pgvector Guide](pgvector.md) — vector store configuration, embedding dimensions, similarity search tuning
- [Local Setup](../getting-started/local-setup.md) — environment variables, Docker Compose flags
- [Architecture](../architecture.md) — how the document store layer fits into the overall system
