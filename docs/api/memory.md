# Memory API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/memories` | Create or upsert a memory |
| `GET` | `/api/memories` | List memories (`agent_id`, `scope`, `tags`) |
| `GET` | `/api/memories/{id}` | Get memory |
| `PUT` | `/api/memories/{id}` | Update memory |
| `DELETE` | `/api/memories/{id}` | Delete memory |
| `POST` | `/api/memories/search` | Search memories |
| `GET` | `/api/memories/stm/{agent_id}` | Inspect current Redis STM cache for an agent |

## Create

```json
{
  "agent_id": "<AGENT_ID>",
  "scope": "agent",
  "key": "user-preference",
  "value": "Prefers concise responses with code examples",
  "metadata": {"tags": ["preferences"]},
  "ttl": "2026-06-01T00:00:00Z"
}
```

Scopes are `session`, `agent`, and `global`. Existing `(agent_id, scope, key)` records are updated rather than duplicated.
