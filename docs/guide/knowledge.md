# Knowledge Bases

Knowledge sources and items provide retrieval-augmented context for agents. Agent and workflow tags select relevant knowledge at runtime.

## API Source Types

The backend API accepts these source types:

| `source_type` | Backend | Notes |
|---|---|---|
| `vector_db` | Qdrant | Semantic `query_points` when a query and embeddings are available; fallback scroll otherwise |
| `mongo_db` | Application document store | Source/item records and GridFS-backed file metadata |
| `pgvector` | PostgreSQL + pgvector | Queries `langchain_pg_embedding_{collection}` for per-source pgvector retrieval |

```bash
curl -X POST http://localhost:8000/api/knowledge-sources \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "product-docs",
    "source_type": "vector_db",
    "connection_config": {"url": "http://qdrant:6333", "collection": "docs"},
    "tags": ["documentation"]
  }'
```

## Flutter UI Forms

The current Flutter Knowledge UI exposes user-facing source kinds such as `text`, `url`, `file`, `git`, and `database` with fields for name, description, source type, and tags. Those forms are UI-level conveniences. API-only automation should use the backend `source_type` values above: `vector_db`, `mongo_db`, or `pgvector`.

The UI item form exposes title/content, source ID, and tags for text-style records. Multipart file upload and GridFS content download are available through the API and may not be exposed in every UI flow.

## Knowledge Items

Text items use `name` and `text_content`:

```bash
curl -X POST http://localhost:8000/api/knowledge-items \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "<SOURCE_ID>",
    "name": "SLA summary",
    "text_content": "Our SLA guarantees 99.9% uptime.",
    "tags": ["sla", "production"]
  }'
```

## Retrieval Behavior

1. If a query is available and `EMBEDDINGS_ENABLED=true`, Qdrant sources use semantic `query_points`.
2. If semantic search is unavailable, Qdrant falls back to scroll-style retrieval.
3. `pgvector` sources call the pgvector adapter, expecting `langchain_pg_embedding_{collection}` tables for per-source retrieval.
4. Local text/source items are selected by tag overlap.
5. Results are injected into the agent system prompt as a `<knowledge>` block within prompt budgets.

Use concise, consistent tags so agents and workflows retrieve only relevant context.
