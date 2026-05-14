# Agent Memory

TBD Agents uses Short-Term Memory (STM) and Long-Term Memory (LTM) so agents can remember information across executions.

| Tier | Store | Purpose |
|---|---|---|
| STM | Redis | Fast recent memories per agent |
| LTM | MongoDB or PostgreSQL | Durable memories with optional embeddings and TTL |

## Retrieval Order

When memory context is requested for a task, the current behavior is:

1. If a query is available and `EMBEDDINGS_ENABLED=true`, attempt semantic vector retrieval.
2. Add Redis STM recent memories.
3. Fall back to or supplement with LTM records from the active document store.
4. Prune expired memories and inject results as a `<memories>` XML block within prompt budgets.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `STM_MAX_ENTRIES` | `20` | Max recent memories cached per agent in Redis |
| `LTM_MAX_ENTRIES` | `200` | Max durable memories per agent; `0` disables cap |
| `MEMORY_RETRIEVAL_TOP_K` | `8` | Semantic memory retrieval limit |
| `EMBEDDINGS_ENABLED` | `true` | Enables semantic memory and knowledge retrieval |

## API Examples

```bash
curl -X POST http://localhost:8000/api/memories \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "scope": "agent",
    "key": "coding-style",
    "value": "Use type hints everywhere."
  }'

curl http://localhost:8000/api/memories/stm/<AGENT_ID> \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

Scopes are `session`, `agent`, and `global`.
