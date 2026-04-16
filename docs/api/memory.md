# Memory API

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/memories` | Create or upsert a memory |
| `GET` | `/api/memories` | List memories (filter by `agent_id`, `scope`, `tags`) |
| `GET` | `/api/memories/{id}` | Get memory by ID |
| `PUT` | `/api/memories/{id}` | Update memory |
| `DELETE` | `/api/memories/{id}` | Delete memory |
| `POST` | `/api/memories/search` | Search memories by keyword |

---

## Create Memory

```
POST /api/memories
```

```json
{
  "agent_id": "6601a1b2c3d4e5f607890abc",
  "scope": "agent",
  "key": "user-preference",
  "value": "Prefers concise responses with code examples",
  "metadata": {"tags": ["preferences"]},
  "ttl": "2025-06-01T00:00:00Z"
}
```

**Scopes:** `session`, `agent`, `global`

If a memory with the same `(agent_id, scope, key)` already exists, it is updated.

### Response (201)

```json
{
  "id": "6601a1b2c3d4e5f607890def",
  "agent_id": "6601a1b2c3d4e5f607890abc",
  "scope": "agent",
  "key": "user-preference",
  "value": "Prefers concise responses with code examples",
  "embedding": null,
  "metadata": {"tags": ["preferences"]},
  "ttl": "2025-06-01T00:00:00Z",
  "created_at": "2025-01-10T10:00:00Z",
  "updated_at": "2025-01-10T10:00:00Z"
}
```

---

## List Memories

```
GET /api/memories?agent_id=AGENT_ID&scope=agent&tags=preferences
```

All query parameters are optional. Without `agent_id`, returns all memories.

### Response (200)

```json
[
  {
    "id": "...",
    "agent_id": "...",
    "scope": "agent",
    "key": "user-preference",
    "value": "Prefers concise responses",
    "embedding": null,
    "metadata": {"tags": ["preferences"]},
    "ttl": null,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

## Get Memory

```
GET /api/memories/{id}
```

### Response (200)

Returns a single memory object. Returns `404` if not found.

---

## Update Memory

```
PUT /api/memories/{id}
```

```json
{
  "value": "Updated preference text",
  "metadata": {"tags": ["preferences", "updated"]}
}
```

All fields are optional. Only provided fields are updated.

---

## Delete Memory

```
DELETE /api/memories/{id}
```

Returns `204` on success, `404` if not found.

---

## Search Memories

```
POST /api/memories/search
```

```json
{
  "agent_id": "6601a1b2c3d4e5f607890abc",
  "query": "preference",
  "scope": "agent",
  "limit": 10
}
```

Searches across `key` and `value` fields using keyword matching. `scope` and `limit` are optional.

### Response (200)

Returns an array of matching memory objects, sorted by most recently updated.
