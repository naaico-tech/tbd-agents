# Agent Memory

TBD Agents provides a two-tier persistent memory system that allows agents to remember information across workflow executions and sessions.

---

## Architecture: STM & LTM

Memory uses a two-tier architecture for optimal performance:

| Tier | Store | Purpose | Access speed |
|---|---|---|---|
| **STM** (Short-Term Memory) | Redis | Last N memories per agent, used for system prompt injection | Sub-millisecond |
| **LTM** (Long-Term Memory) | MongoDB or PostgreSQL document store | Up to M memories per agent, queryable via API | Standard DB |
| **Semantic memory** | Qdrant or pgvector | Optional vector recall when embeddings are enabled | Similarity search |

### How the tiers interact

1. **Writes** go to both MongoDB (LTM) and Redis (STM) simultaneously
2. **Reads for context injection** use semantic vector recall first when a query is available and `EMBEDDINGS_ENABLED=true`
3. The engine then reads Redis STM and falls back to LTM if STM is empty or unavailable
4. **Search/query operations** use the document store fields for keyword-style API search
5. **On startup**, a warmup process loads recent memories for all agents from LTM into Redis

### Configuration

| Setting | Default | Description |
|---|---|---|
| `STM_MAX_ENTRIES` | `20` | Max recent memories per agent cached in Redis |
| `LTM_MAX_ENTRIES` | `200` | Max memories per agent in MongoDB (0 = unlimited) |
| `EMBEDDINGS_ENABLED` | `true` | Enable semantic memory and knowledge retrieval |
| `MEMORY_RETRIEVAL_TOP_K` | `8` | Max semantic memory matches for prompt context |

Set via environment variables or `.env` file.

---

## Memory Scopes

Memories are organized into three scopes:

| Scope | Description | Visibility |
|---|---|---|
| `session` | Per-workflow execution | Only within the specific workflow run |
| `agent` | Per-agent, across workflows | Shared across all workflows for one agent |
| `global` | Shared across all agents | Available to every agent in the system |

---

## How Memory Works

### Reading (automatic)

Before each agent execution, the engine automatically:

1. Uses semantic vector retrieval when a query is available and embeddings are enabled
2. Checks **Redis STM** for cached recent memories (fast path)
3. Falls back to **LTM** in the selected document store if STM is empty or unavailable
4. Prunes any expired memories (TTL-based)
5. Injects all memories as a `<memories>` XML block in the system prompt

```xml
<memories>
<memory key="user-preference" scope="agent">
Prefers concise responses with code examples.
</memory>
<memory key="project-context" scope="global">
Using Python 3.12 and FastAPI.
</memory>
</memories>
```

### Writing (via tool)

Agents can store memories during execution using the built-in `store_memory` tool. The agent decides what to remember:

```
store_memory(key="deployment-preference", value="Always use blue-green deployments", scope="agent")
```

The `store_memory` tool is automatically available to agents running through the Claude SDK and custom provider paths. It accepts:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `key` | string | Yes | Short descriptive key for the memory |
| `value` | string | Yes | The content to remember |
| `scope` | string | No | `session`, `agent` (default), or `global` |
| `metadata` | object | No | Optional metadata tags |

### Upsert Behavior

When storing a memory with a `(agent_id, scope, key)` combination that already exists, the value is updated (upserted) rather than creating a duplicate.

---

## TTL & Pruning

Memories can have an optional TTL (time-to-live). Expired memories are automatically pruned before each agent execution.

Set TTL when creating memories via the API:

```bash
curl -X POST http://localhost:8000/api/memories \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "AGENT_ID",
    "scope": "session",
    "key": "temp-context",
    "value": "Working on ticket #123",
    "ttl": "2025-01-15T12:00:00Z"
  }'
```

---

## API Usage Examples

### Store a memory

```bash
curl -X POST http://localhost:8000/api/memories \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "AGENT_ID",
    "scope": "agent",
    "key": "coding-style",
    "value": "Use type hints everywhere. Prefer dataclasses over dicts."
  }'
```

### List agent memories

```bash
curl http://localhost:8000/api/memories?agent_id=AGENT_ID&scope=agent \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

### Search memories

```bash
curl -X POST http://localhost:8000/api/memories/search \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "AGENT_ID",
    "query": "coding style"
  }'
```

### Delete a memory

```bash
curl -X DELETE http://localhost:8000/api/memories/MEMORY_ID \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

---

## LTM Cap & Cleanup

When `LTM_MAX_ENTRIES` is set (default: 200), the system automatically removes the oldest memories for an agent when the cap is exceeded. This happens on every `store` operation. Set to `0` to disable the cap.

STM entries are automatically trimmed to `STM_MAX_ENTRIES` (default: 20) per agent using a Redis sorted set scored by timestamp.

---

## Integration with Knowledge

Memory and Knowledge are complementary systems:

| Feature | Knowledge | Memory |
|---|---|---|
| **Source** | External data (docs, DBs) | Agent-generated observations |
| **Mutability** | Managed by users | Written by agents and users |
| **Scope** | Shared via tags and sources | Per-agent, per-session, or global |
| **Lifecycle** | Persistent until deleted | Optional TTL-based expiry |

Both are injected into the system prompt before each execution.
