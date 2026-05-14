---
icon: material/database-export
---

# Import & Export

Import/export lets you back up configuration and move resources between environments.

## API Support

| Resource | Export | Import |
|---|---|---|
| Full bundle | `GET /api/export` | `POST /api/import` |
| Agents | `GET /api/agents/export`, `GET /api/agents/{id}/export` | `POST /api/agents/import` |
| Skills | `GET /api/skills/export`, `GET /api/skills/{id}/export` | `POST /api/skills/import` |
| Workflows | `GET /api/workflows/export`, `GET /api/workflows/{id}/export` | `POST /api/workflows/import` |
| Knowledge Sources | `GET /api/knowledge-sources/export`, `GET /api/knowledge-sources/{id}/export` | `POST /api/knowledge-sources/import` |

## Flutter UI Support

The current Flutter UI exposes import/export buttons for **Agents**, **Skills**, and **Workflows** only. Full-system bundles and Knowledge Source import/export are API-only even though endpoints exist.

## Valid Knowledge Source Example

Use one of the backend source types: `vector_db`, `mongo_db`, or `pgvector`.

```json
{
  "name": "runbooks",
  "description": "Internal runbook vector store",
  "source_type": "vector_db",
  "connection_config": {
    "url": "http://qdrant:6333",
    "collection": "runbooks"
  },
  "tags": ["ops"]
}
```

## Import Behavior

- Imports create new documents; they do not update or deduplicate by name.
- Batch imports collect per-item errors and continue processing the rest.
- Workflow imports validate `agent_id`; import agents before workflows.
- Imported workflows are assigned to the authenticated GitHub user.
