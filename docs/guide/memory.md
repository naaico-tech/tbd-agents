# Agent Memory

TBD Agents provides a built-in persistent memory system that allows agents to remember information across workflow executions and sessions.

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

1. Fetches **agent-scope** memories for the current agent
2. Fetches **global-scope** memories shared across all agents
3. Fetches **session-scope** memories for the current workflow
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

## Integration with Knowledge

Memory and Knowledge are complementary systems:

| Feature | Knowledge | Memory |
|---|---|---|
| **Source** | External data (docs, DBs) | Agent-generated observations |
| **Mutability** | Managed by users | Written by agents and users |
| **Scope** | Shared via tags and sources | Per-agent, per-session, or global |
| **Lifecycle** | Persistent until deleted | Optional TTL-based expiry |

Both are injected into the system prompt before each execution.
