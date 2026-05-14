# Knowledge API

## Knowledge Sources

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/knowledge-sources` | Register knowledge source |
| `GET` | `/api/knowledge-sources` | List sources (optional `?tags=` filter) |
| `GET` | `/api/knowledge-sources/{id}` | Get source |
| `PUT` | `/api/knowledge-sources/{id}` | Update source |
| `DELETE` | `/api/knowledge-sources/{id}` | Delete source (cascade-deletes items) |
| `POST` | `/api/knowledge-sources/{id}/test` | Test connection |
| `GET` | `/api/knowledge-sources/export` | Export all knowledge sources |
| `GET` | `/api/knowledge-sources/{id}/export` | Export one knowledge source |
| `POST` | `/api/knowledge-sources/import` | Import knowledge sources |

### Register Source

```
POST /api/knowledge-sources
```

```json
{
  "name": "product-docs",
  "source_type": "vector_db",
  "connection_config": {"url": "http://qdrant:6333", "collection": "docs"},
  "tags": ["documentation"]
}
```

Source types: `vector_db`, `mongo_db`, `pgvector`.

For per-source pgvector retrieval use:

```json
{
  "name": "postgres-docs",
  "description": "Documentation embeddings in PostgreSQL",
  "source_type": "pgvector",
  "connection_config": {
    "dsn": "postgresql+asyncpg://user:pass@host:5432/dbname",
    "collection": "docs"
  },
  "tags": ["documentation"]
}
```

---

## Knowledge Items

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/knowledge-items` | Create text knowledge item |
| `POST` | `/api/knowledge-items/upload` | Upload file/image (multipart) |
| `GET` | `/api/knowledge-items` | List items (`?source_id=`, `?tags=`, `?content_type=`) |
| `GET` | `/api/knowledge-items/{id}` | Get item metadata |
| `GET` | `/api/knowledge-items/{id}/content` | Download file content |
| `PUT` | `/api/knowledge-items/{id}` | Update item tags/metadata |
| `DELETE` | `/api/knowledge-items/{id}` | Delete item |
| `POST` | `/api/knowledge-items/query` | Query items by tags |

### Create Text Item

```
POST /api/knowledge-items
```

```json
{
  "source_id": "<SOURCE_ID>",
  "name": "SLA summary",
  "text_content": "Our SLA guarantees 99.9% uptime.",
  "tags": ["sla", "production"]
}
```

`content_type` defaults to `text`; file and image content should use the upload endpoint.

### Upload File

```
POST /api/knowledge-items/upload
Content-Type: multipart/form-data
```

```bash
curl -X POST http://localhost:8000/api/knowledge-items/upload \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -F "file=@runbook.pdf" \
  -F "source_id=<SOURCE_ID>" \
  -F "tags=runbook,ops"
```

### Query Items

```
POST /api/knowledge-items/query
```

```json
{
  "tags": ["sla"]
}
```
