# PostgreSQL pgvector Backend

> **New in this release** — TBD Agents now supports PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector) extension as an alternative vector store backend alongside Qdrant.

## Overview

[pgvector](https://github.com/pgvector/pgvector) is a PostgreSQL extension that adds a native `vector` data type and efficient similarity-search operators (`<=>`, `<->`, `<#>`). Choosing pgvector as your vector store backend makes sense when:

- You already run PostgreSQL in your stack and want to avoid operating a separate Qdrant service.
- You need ACID guarantees — vector writes participate in normal PostgreSQL transactions.
- You want to join vector results with relational data using standard SQL.
- Your dataset is stable enough that IVFFlat indexing gives acceptable recall (see [Indexing Strategy](#indexing-strategy)).

If you need sub-millisecond search over hundreds of millions of vectors, or you are already committed to Qdrant, the existing `vector_db` source type remains fully supported and is unaffected by this change.

---

## Prerequisites

- **PostgreSQL 14+** with the `vector` extension installed.
- **OR Docker** — the bundled `pgvector/pgvector:pg16` image ships with the extension pre-installed and is the recommended choice for local development.
- Python extras: `asyncpg>=0.29.0` and `pgvector>=0.3.0` (add the `pgvector` optional-dependency group; see [pyproject.toml](../../pyproject.toml)).

---

## Quick Start with Docker

The recommended way to select a vector store backend is via the `COMPOSE_PROFILES`
variable in your `.env` file:

```env
# .env — choose one
COMPOSE_PROFILES=pgvector    # start pgvector
# COMPOSE_PROFILES=qdrant   # (default) start Qdrant instead
```

Then start the stack normally:

```bash
docker compose up
```

Or, to start only the pgvector container without the full stack:

```bash
docker compose --profile pgvector up pgvector
```

Verify the extension is available:

```bash
docker exec -it tbd-pgvector psql -U postgres -d tbd_agents \
  -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
```

Expected output:

```
 extversion
------------
 0.8.0
(1 row)
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VECTOR_STORE_BACKEND` | `qdrant` | Active backend — set to `pgvector` to switch |
| `PGVECTOR_DSN` | — | asyncpg-compatible connection string (required when backend is `pgvector`) |
| `PGVECTOR_TABLE_PREFIX` | `vs` | Prefix prepended to every collection table name |
| `PGVECTOR_USER` | `postgres` | Postgres username (Docker service only) |
| `PGVECTOR_PASSWORD` | `postgres` | Postgres password (Docker service only) |
| `PGVECTOR_DB` | `tbd_agents` | Database name (Docker service only) |
| `PGVECTOR_PORT` | `5432` | Host port mapped to the container (Docker service only) |

### `.env` snippet — Docker pgvector service

```bash
VECTOR_STORE_BACKEND=pgvector
PGVECTOR_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents
PGVECTOR_TABLE_PREFIX=vs
```

### Connecting to an existing PostgreSQL instance

Replace the DSN with your own connection string. The database user requires `CREATE TABLE` and `CREATE INDEX` privileges on the target schema:

```bash
VECTOR_STORE_BACKEND=pgvector
PGVECTOR_DSN=postgresql+asyncpg://myuser:mypassword@db.example.com:5432/production
PGVECTOR_TABLE_PREFIX=tbd
```

The `vector` extension must already be installed in the target database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Using pgvector as a Knowledge Source

There are two independent ways to use pgvector in TBD Agents.

### 1. Global Backend (Memories + Agent Knowledge)

Set `VECTOR_STORE_BACKEND=pgvector` in your environment. The memory manager will automatically create and query the `vs_agent_memories` table (or `{PGVECTOR_TABLE_PREFIX}_agent_memories` if you customise the prefix) for all agent memory operations.

This affects **all** agents and workflows; their long-term semantic memory is now stored in PostgreSQL instead of Qdrant.

### 2. Per-Source Knowledge Base (Knowledge Sources API)

Create a knowledge source with `source_type: "pgvector"` and its own DSN. This is useful when:

- Different knowledge bases live in different databases or schemas.
- You want to keep memory vectors in Qdrant while querying a legacy PostgreSQL corpus for knowledge retrieval (or vice-versa).
- A third-party system already populates a `langchain_pg_embedding_*` table you want to query.

```bash
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -d '{
    "name": "Product Docs",
    "source_type": "pgvector",
    "connection_config": {
      "dsn": "postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents",
      "collection": "product_docs"
    },
    "tags": ["product", "docs"]
  }'
```

**`connection_config` fields for `pgvector` sources:**

| Field | Required | Description |
|---|---|---|
| `dsn` | Yes (or `dsn_token_name`) | asyncpg DSN for the target database |
| `collection` | Yes | Table name suffix; the adapter queries `langchain_pg_embedding_{collection}` |
| `dsn_token_name` | No | Name of a stored token whose value is the DSN — overrides `dsn` when set |

Storing the DSN as a token avoids embedding credentials in the source definition:

```bash
# Store the DSN as an encrypted token
curl -X POST http://localhost:8000/api/tokens \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "pgvector-dsn", "value": "postgresql+asyncpg://user:pass@host/db"}'

# Reference it in the source
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -d '{
    "name": "Secure Vectors",
    "source_type": "pgvector",
    "connection_config": {
      "dsn_token_name": "pgvector-dsn",
      "collection": "product_docs"
    },
    "tags": ["product"]
  }'
```

### Testing a connection

```bash
curl -X POST http://localhost:8000/api/knowledge-sources/<SOURCE_ID>/test \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

The test endpoint connects to the database and verifies that the `vector` extension is installed. Returns `{"success": true}` on success or `{"success": false, "error": "..."}` with details.

---

## Schema

The adapter automatically creates two types of tables on first use.

### Collection tables

Each collection maps to a table named `{table_prefix}_{collection}`:

```sql
CREATE TABLE IF NOT EXISTS vs_<collection> (
    id          TEXT        PRIMARY KEY,
    vector      vector(<dim>),
    payload     JSONB       DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS vs_<collection>_vector_idx
    ON vs_<collection>
    USING ivfflat (vector vector_cosine_ops)
    WITH (lists = 100);
```

### Collections registry

A single `vs_collections` metadata table tracks every collection's vector dimension and distance metric so the correct distance operator is selected at query time:

```sql
CREATE TABLE IF NOT EXISTS vs_collections (
    name        TEXT        PRIMARY KEY,
    vector_size INT         NOT NULL,
    distance    TEXT        NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Indexing Strategy

The adapter creates an **IVFFlat** index by default. Choose the right index type for your workload:

| Index | Best for | Trade-offs |
|---|---|---|
| **IVFFlat** (default) | Bulk-loaded, stable datasets | Requires `VACUUM ANALYZE` after large bulk inserts to update statistics; lower memory than HNSW |
| **HNSW** | High-recall requirements; datasets with frequent inserts | Higher build-time memory; no `VACUUM ANALYZE` needed for recall to stay accurate |

### Switching to HNSW

Drop the existing IVFFlat index and replace it with an HNSW index. This is a one-off manual operation; the adapter does not auto-migrate existing indexes:

```sql
DROP INDEX IF EXISTS vs_product_docs_vector_idx;

CREATE INDEX vs_product_docs_vector_idx
    ON vs_product_docs
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

Tune `m` (max connections per node, default 16) and `ef_construction` (size of the dynamic candidate list at build time, default 64) to trade build time and memory for recall accuracy.

### After bulk inserts (IVFFlat only)

Run `VACUUM ANALYZE` after loading large batches so PostgreSQL picks up the new row statistics and the query planner correctly selects the vector index:

```sql
VACUUM ANALYZE vs_product_docs;
```

---

## Observability

### Index Usage

Confirm the query planner is using the vector index rather than a sequential scan:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, 1 - (vector <=> '[0.1,0.2,...]'::vector) AS score
FROM   vs_product_docs
ORDER  BY vector <=> '[0.1,0.2,...]'::vector
LIMIT  10;
```

Look for `Index Scan using vs_product_docs_vector_idx` in the plan output. A `Seq Scan` indicates the index is missing, the table is empty, or statistics are stale.

### Collection Statistics

```sql
SELECT
    c.name              AS collection,
    c.vector_size,
    c.distance,
    pg_size_pretty(pg_relation_size('vs_' || c.name)) AS table_size,
    s.n_live_tup        AS live_rows,
    s.n_dead_tup        AS dead_rows
FROM vs_collections c
LEFT JOIN pg_stat_user_tables s ON s.relname = 'vs_' || c.name;
```

### Index Hit Rate

```sql
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname LIKE 'vs_%';
```

### Connection Pool Health

```sql
SELECT count(*), state, wait_event_type
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type;
```

### Key Metrics to Monitor

- **Query latency (p95)** — vector search over a well-indexed collection should complete in under 100 ms.
- **Index scan ratio** — aim for > 95 % of vector queries using an index scan rather than a sequential scan.
- **Dead tuple ratio** — trigger `VACUUM ANALYZE` when `n_dead_tup / n_live_tup` exceeds 10 %.
- **Connection pool utilisation** — the adapter defaults to `pool_min=2`, `pool_max=10`; raise `pool_max` if you see connection wait events under load.

---

## Migrating from Qdrant

To switch vector stores at deploy time, update `COMPOSE_PROFILES` in your `.env` (and set `VECTOR_STORE_BACKEND` to match), then restart the stack:

```env
# .env
COMPOSE_PROFILES=pgvector
VECTOR_STORE_BACKEND=pgvector
```

```bash
docker compose up
```

That is the only change needed to the Compose setup — no `docker-compose.yml` edits required.

Switching `VECTOR_STORE_BACKEND` from `qdrant` to `pgvector` only affects the **global memory store** used by `memory_manager`. It does **not** affect existing `vector_db` (Qdrant) knowledge sources — those continue to work exactly as before regardless of the global backend setting.

**Memory data is not automatically migrated.** If you need to carry over existing agent memories:

1. Export memory payloads from Qdrant using the Qdrant REST API or snapshot tooling.
2. Re-ingest them via the `/api/memories` endpoint (or directly via `PgvectorAdapter.upsert()`).

If you only want to use pgvector for new knowledge sources while keeping Qdrant as the global memory backend, leave `VECTOR_STORE_BACKEND=qdrant` and create per-source pgvector sources as described in [Per-Source Knowledge Base](#2-per-source-knowledge-base-knowledge-sources-api).

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ERROR: type "vector" does not exist` | pgvector extension not installed in the database | `CREATE EXTENSION IF NOT EXISTS vector;` |
| Slow queries / sequential scan in `EXPLAIN` | Index not yet built, empty table, or stale statistics | `VACUUM ANALYZE vs_<collection>;` |
| `connection refused` on port 5432 | pgvector container not running | Set `COMPOSE_PROFILES=pgvector` in `.env` and run `docker compose up` |
| `asyncpg.UndefinedTableError` during search | Collection table does not exist | Call `store.create_collection()` first, or add items via the API — the adapter creates the table automatically |
| `{"success": false, "error": "pgvector extension is not installed..."}` on test | Extension missing | Connect to the DB as a superuser and run `CREATE EXTENSION IF NOT EXISTS vector;` |
| Index not used after bulk insert | IVFFlat statistics are stale | `VACUUM ANALYZE vs_<collection>;` |
| High memory usage on startup | HNSW index loaded into `shared_buffers` | Tune `shared_buffers` in `postgresql.conf`, or switch to IVFFlat for memory-constrained environments |
