# Knowledge Bases

TBD Agents supports knowledge sources and items for retrieval-augmented generation (RAG). Connect vector databases or MongoDB collections so agents have access to your domain knowledge.

---

## Knowledge Sources

A knowledge source represents a connection to a data backend:

| Type | Description |
|---|---|
| `vector_db` | Vector database for semantic search |
| `mongo_db` | MongoDB collection for structured queries |

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

### Testing a connection

```bash
curl -X POST http://localhost:8000/api/knowledge-sources/<ID>/test \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

---

## Knowledge Items

Items represent individual pieces of knowledge stored within a source.

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

### Uploading a file

```bash
curl -X POST http://localhost:8000/api/knowledge-items/upload \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -F "file=@runbook.pdf" \
  -F "source_id=<SOURCE_ID>" \
  -F "tags=runbook,ops"
```

### Querying items

```bash
curl -X POST http://localhost:8000/api/knowledge-items/query \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["sla"]}'
```

---

## Filtering

Knowledge items support filtering by:

| Parameter | Description |
|---|---|
| `source_id` | Items from a specific source |
| `tags` | Items matching specific tags |
| `content_type` | Filter by content type (text, file, image) |
