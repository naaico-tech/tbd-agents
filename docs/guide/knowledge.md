# Knowledge Bases

TBD Agents supports knowledge sources and items for retrieval-augmented generation (RAG). Connect vector databases or MongoDB collections so agents have access to your domain knowledge at runtime.

---

## Architecture Overview

Knowledge is organised into two layers:

- **Knowledge Sources** — connection definitions pointing at a data backend (Qdrant vector DB or MongoDB).
- **Knowledge Items** — individual pieces of knowledge stored within a source (text snippets, uploaded files, images).

When an agent executes, the engine calls `build_knowledge_context()` to aggregate relevant items into an XML block that is injected into the system prompt. Items are selected by matching **tags** on the agent or workflow against tags on items and sources.

```
Agent / Workflow tags ──▶ Knowledge Items (MongoDB)
                         ──▶ Knowledge Sources (Qdrant) ──▶ Vector scroll results
```

The combined context is wrapped in `<knowledge>` XML and appended to the system prompt before sending to the LLM.

---

## Knowledge Sources

A knowledge source represents a connection to a data backend:

| Type | Backend | Description |
|---|---|---|
| `vector_db` | Qdrant | Semantic search over vector-embedded documents |
| `mongo_db` | MongoDB | Structured storage with tag-based retrieval |
| `pgvector` | PostgreSQL + pgvector | Semantic search backed by a PostgreSQL database with the `vector` extension |

### pgvector Sources

The `pgvector` source type lets you connect TBD Agents to any PostgreSQL 14+ database that has the [pgvector](https://github.com/pgvector/pgvector) extension installed. This is useful when your knowledge corpus already lives in Postgres, or when you prefer a single-database stack over a separate Qdrant service.

A pgvector source performs semantic similarity search when a query string is available and embeddings are enabled; it falls back to a recency-ordered scan when no query is provided.

**`connection_config` fields for `pgvector` sources:**

| Field | Required | Description |
|---|---|---|
| `dsn` | Yes (or `dsn_token_name`) | asyncpg-compatible PostgreSQL connection string |
| `collection` | Yes | Table name suffix used to identify the target table |
| `dsn_token_name` | No | Name of a stored token whose value is the DSN — overrides `dsn` when set |

For setup instructions, Docker Compose usage, indexing options, and observability queries, see the [PostgreSQL pgvector Backend](pgvector.md) guide.

### Source Lifecycle

Each source has a status:

| Status | Meaning |
|---|---|
| `registered` | Source created but not yet tested |
| `connected` | Connection tested successfully |
| `error` | Last connection test failed (see `last_error`) |

### Registering a source

```bash
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "product-docs",
    "type": "vector_db",
    "connection_config": {"url": "http://qdrant:6333", "collection": "docs"},
    "tags": ["documentation"]
  }'
```

### Qdrant Vector DB Setup

To use a Qdrant source you need a running Qdrant instance. The `docker-compose.yml` includes Qdrant by default.

**connection_config fields for `vector_db`:**

| Field | Required | Description |
|---|---|---|
| `url` | Yes | Qdrant HTTP endpoint (e.g. `http://qdrant:6333`) |
| `collection` | Yes | Name of the Qdrant collection to query |
| `api_key_token_name` | No | Name of a stored token containing the Qdrant API key |

If your Qdrant instance requires authentication, first store the API key as a token:

```bash
# Store the API key
curl -X POST http://localhost:8000/api/tokens \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "qdrant-key", "value": "your-qdrant-api-key"}'

# Reference it in the source
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "secure-vectors",
    "type": "vector_db",
    "connection_config": {
      "url": "https://qdrant.example.com:6333",
      "collection": "embeddings",
      "api_key_token_name": "qdrant-key"
    },
    "tags": ["embeddings"]
  }'
```

### MongoDB Source

MongoDB sources use the same database as TBD Agents itself. No additional `connection_config` is needed — status always moves to `connected` on test.

```bash
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "internal-docs",
    "type": "mongo_db",
    "tags": ["internal"]
  }'
```

### Testing a connection

```bash
curl -X POST http://localhost:8000/api/knowledge-sources/<ID>/test \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

Returns `{"success": true}` on success or `{"success": false, "error": "..."}` with details.

---

## Knowledge Items

Items represent individual pieces of knowledge stored within a source. There are three content types:

| Content Type | Storage | Description |
|---|---|---|
| `text` | MongoDB document | Plain text stored in `text_content` field |
| `file` | GridFS | Binary file (PDF, DOCX, etc.) stored via MongoDB GridFS |
| `image` | GridFS | Image file stored via MongoDB GridFS |

### Creating a text item

```bash
curl -X POST http://localhost:8000/api/knowledge-items \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "<SOURCE_ID>",
    "content": "Our SLA guarantees 99.9% uptime for production services.",
    "tags": ["sla", "production"]
  }'
```

### Uploading a file (GridFS)

Binary files are stored in MongoDB GridFS, which handles arbitrarily large files by chunking them. The API accepts multipart form uploads:

```bash
curl -X POST http://localhost:8000/api/knowledge-items/upload \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -F "file=@runbook.pdf" \
  -F "source_id=<SOURCE_ID>" \
  -F "tags=runbook,ops"
```

The upload endpoint:

1. Reads the file bytes from the multipart request
2. Opens a GridFS upload stream with the original filename
3. Writes the file content and closes the stream
4. Creates a `KnowledgeItem` record with `file_id` pointing to the GridFS object

Uploaded files can be retrieved or deleted through the items API. Deleting an item also removes its associated GridFS file.

### Querying items

```bash
# Query by tags
curl -X POST http://localhost:8000/api/knowledge-items/query \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["sla"]}'

# List all items for a source
curl "http://localhost:8000/api/knowledge-items?source_id=<SOURCE_ID>" \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

---

## Retrieval Behaviour

When an agent runs, the engine resolves knowledge context through two paths:

### 1. Tag-based retrieval (MongoDB items)

Items whose `tags` overlap with the agent or workflow tags are fetched directly from MongoDB. Up to 50 items are retrieved per execution. Each text item is wrapped in an XML `<item>` element:

```xml
<knowledge>
  <item name="sla-doc" tags="sla,production">
    Our SLA guarantees 99.9% uptime for production services.
  </item>
</knowledge>
```

### 2. Vector scroll (Qdrant sources)

For each `vector_db` source attached to the agent, the engine calls `query_vector_db()` which uses Qdrant's scroll API to retrieve up to 20 documents with their payloads. Each result's `text` payload field is wrapped in an XML `<item>` element:

```xml
<knowledge>
  <item source="product-docs">
    Document text from the vector database...
  </item>
</knowledge>
```

!!! note "Phase 1 Limitation"
    The current implementation uses Qdrant **scroll** (not semantic search). Full embedding-based search with query vectors will be added in a future release.

### Context injection

The aggregated `<knowledge>` block is appended to the system prompt before each LLM call. This ensures the model has access to relevant domain knowledge regardless of which provider (Copilot, Claude, or BYOK) is used.

---

## Filtering

Knowledge items support filtering by:

| Parameter | Description |
|---|---|
| `source_id` | Items from a specific source |
| `tags` | Items matching specific tags |
| `content_type` | Filter by content type (`text`, `file`, `image`) |

---

## Best Practices

- **Use descriptive tags** — agents select knowledge items by tag matching, so consistent tagging is critical.
- **Keep text items focused** — shorter, topic-specific items produce better results than large monolithic documents.
- **Test connections after creation** — always call the `/test` endpoint to verify Qdrant connectivity.
- **Rotate API keys via tokens** — store Qdrant API keys as TBD Agents tokens and reference them by name in `connection_config`. This avoids embedding secrets in source definitions.
- **Monitor source status** — sources in `error` status will be skipped during retrieval. Check `last_error` for diagnostics.
