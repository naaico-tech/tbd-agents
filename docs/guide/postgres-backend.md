# PostgreSQL Backend Guide

TBD Agents supports a fully-PostgreSQL deployment stack via the `pgvector` profile.
This guide covers everything you need to know to run, configure, migrate to, and
operate the PostgreSQL backend.

---

## Overview

By default TBD Agents uses **MongoDB** as its document store (the `qdrant` profile).
The `pgvector` profile replaces MongoDB with **PostgreSQL 17**, using JSONB columns
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
| **Document store** | MongoDB 7 | PostgreSQL 17 (JSONB) |
| **Vector store** | Qdrant | pgvector extension |
| **Services needed** | 2 (`mongodb` + `qdrant`) | 1 (`postgres` with pgvector) |
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
POSTGRES_URI=postgresql+asyncpg://postgres:postgres@postgres:5432/tbd_agents
```

### 2. Start services

```bash
docker compose up -d
```

This starts a single `postgres` container with the pgvector extension pre-installed.
No MongoDB, no Qdrant.

### 3. Apply database migrations

```bash
docker compose exec app alembic upgrade head
```

### 4. Verify

```bash
docker compose ps          # postgres should be Up
docker compose exec app alembic current   # should show head revision
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DB_BACKEND` | `mongo` | Document store backend: `mongo` or `postgres` |
| `POSTGRES_URI` | `postgresql+asyncpg://postgres:postgres@postgres:5432/tbd_agents` | Async-compatible PostgreSQL connection string (uses `asyncpg` driver) |
| `POSTGRES_DB_NAME` | `tbd_agents` | PostgreSQL database name |
| `COMPOSE_PROFILES` | _(none)_ | Docker Compose profile: `qdrant` or `pgvector` |
| `VECTOR_STORE_BACKEND` | `qdrant` | Vector store backend: `qdrant` or `pgvector` — must match `COMPOSE_PROFILES` |

> **Important:** `DB_BACKEND=postgres` and `COMPOSE_PROFILES=pgvector` must always be set
> together. Using one without the other will result in a mismatch between the running
> containers and the application's data layer.

---

## Schema Design

The PostgreSQL backend maps each logical MongoDB collection to a dedicated table.
Each table follows the same pattern: a primary-key `id` column, a `data JSONB` column
that holds the document payload, and `created_at` / `updated_at` timestamps.

```sql
-- Example: the agents table
CREATE TABLE agents (
    id         TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    data       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- GIN index enables fast key/value lookups inside the JSONB payload
CREATE INDEX idx_agents_gin ON agents USING gin(data);
```

### All 15 tables

| Table | Maps to (MongoDB collection) |
|---|---|
| `agents` | agents |
| `chat_sessions` | chat\_sessions |
| `chat_messages` | chat\_messages |
| `memories` | memories |
| `skills` | skills |
| `tokens` | tokens |
| `providers` | providers |
| `knowledge_items` | knowledge\_items |
| `knowledge_sources` | knowledge\_sources |
| `custom_tools` | custom\_tools |
| `guardrails` | guardrails |
| `workflows` | workflows |
| `task_executions` | task\_executions |
| `scheduled_agents` | scheduled\_agents |
| `mcp_servers` | mcp\_servers |

Each table carries the same GIN index pattern (`idx_<table>_gin ON <table> USING gin(data)`)
to accelerate arbitrary JSONB key lookups without needing to define individual columns.

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
alembic revision --autogenerate -m "describe_your_change"
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
python scripts/migrate_mongo_to_postgres.py \
  --mongo-uri    mongodb://localhost:27017 \
  --mongo-db     copilot_agent_hub \
  --postgres-uri postgresql://postgres:postgres@localhost:5432/tbd_agents \
  [--dry-run]                              # preview without writing any data
  [--collections agents,skills,memories]  # migrate specific collections only
```

| Flag | Description |
|---|---|
| `--dry-run` | Print what would be migrated without touching PostgreSQL |
| `--collections` | Comma-separated list of collections to migrate (default: all 15) |

### Verify the migration

```bash
python scripts/verify_migration.py \
  --mongo-uri    mongodb://localhost:27017 \
  --postgres-uri postgresql://postgres:postgres@localhost:5432/tbd_agents
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
SELECT id, data->>'name' AS name, created_at
FROM agents
ORDER BY created_at DESC
LIMIT 10;
```

### Query by JSONB field value

```sql
-- All agents using a specific model
SELECT id, data->>'name' AS name, data->>'model' AS model
FROM agents
WHERE data->>'model' = 'claude-opus-4-5';
```

### Aggregate across embedded fields

```sql
-- Memory count per agent
SELECT
    data->>'agent_id' AS agent_id,
    COUNT(*)          AS memories
FROM memories
GROUP BY data->>'agent_id'
ORDER BY memories DESC;
```

### Index usage health check

```sql
-- Confirm GIN indexes are being used
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE indexrelname LIKE '%gin%'
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
| `connection refused` on startup | PostgreSQL not running or wrong profile active | Verify `COMPOSE_PROFILES=pgvector` in `.env`; run `docker compose ps` to confirm the `postgres` container is `Up` |
| `relation "agents" does not exist` | Tables have not been created | Run `alembic upgrade head` inside the app container |
| `column "data" is of type jsonb but expression is of type text` | asyncpg JSONB serializer not configured | Ensure `json_serializer` / `json_deserializer` are set in the SQLAlchemy engine config (see `app/db.py`) |
| App still reads/writes MongoDB | `DB_BACKEND` not set to `postgres` | Add `DB_BACKEND=postgres` to `.env` and restart the app |
| Slow JSONB queries | GIN index missing or not being used | Run `CREATE INDEX CONCURRENTLY idx_<table>_gin ON <table> USING gin(data);` — no downtime required |
| pgvector extension not found | PostgreSQL image without pgvector | Use the `pgvector/pgvector:pg17` image (configured automatically by the `pgvector` compose profile) |
| Migration script fails with permission errors | PostgreSQL user lacks `CREATE` privilege | Grant superuser or `CREATE ON DATABASE` to the connection user |

---

## See Also

- [pgvector Guide](pgvector.md) — vector store configuration, embedding dimensions, similarity search tuning
- [Local Setup](../getting-started/local-setup.md) — environment variables, Docker Compose flags
- [Architecture](../architecture.md) — how the document store layer fits into the overall system
