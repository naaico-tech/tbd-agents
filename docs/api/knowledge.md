# Knowledge API

## Knowledge Sources

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/knowledge-sources` | Register source |
| `GET` | `/api/knowledge-sources` | List sources (`?tags=` supported) |
| `GET` | `/api/knowledge-sources/export` | Export all sources |
| `GET` | `/api/knowledge-sources/{id}/export` | Export one source |
| `POST` | `/api/knowledge-sources/import` | Import source bundle |
| `GET` | `/api/knowledge-sources/{id}` | Get source |
| `PUT` | `/api/knowledge-sources/{id}` | Update source |
| `DELETE` | `/api/knowledge-sources/{id}` | Delete source and items |
| `POST` | `/api/knowledge-sources/{id}/test` | Test connection |

Valid `source_type` values are `vector_db`, `mongo_db`, and `pgvector`.

```json
{
  "name": "product-docs",
  "description": "Qdrant document vectors",
  "source_type": "vector_db",
  "connection_config": {"url": "http://qdrant:6333", "collection": "docs"},
  "tags": ["documentation"]
}
```

## Knowledge Items

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/knowledge-items` | Create text item |
| `POST` | `/api/knowledge-items/upload` | Upload file/image (multipart) |
| `GET` | `/api/knowledge-items` | List items (`?source_id=`, `?tags=`, `?content_type=`) |
| `GET` | `/api/knowledge-items/{id}` | Get item metadata |
| `GET` | `/api/knowledge-items/{id}/content` | Download file content |
| `PUT` | `/api/knowledge-items/{id}` | Update item |
| `DELETE` | `/api/knowledge-items/{id}` | Delete item |
| `POST` | `/api/knowledge-items/query` | Query by tags |

Create text item body:

```json
{
  "source_id": "<SOURCE_ID>",
  "name": "SLA summary",
  "content_type": "text",
  "text_content": "Our SLA guarantees 99.9% uptime.",
  "tags": ["sla", "production"],
  "metadata": {}
}
```

`name` is required. Text content belongs in `text_content`, not `content`.
