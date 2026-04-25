# Chat API

Conversational interface for talking to your agents.  
Sessions are multi-turn and persisted in MongoDB.  All tokens stream via SSE.

---

## Authentication

Same as all other endpoints — pass a GitHub token:

```http
Authorization: Bearer <github_token>
```

Sessions are **scoped to the authenticated user** — you can only read and write your own sessions.

---

## Endpoints

### POST `/api/agents/{agent_id}/chat`

Send a message to an agent and receive a streaming SSE response.

Omit `session_id` to start a new conversation; include it to continue an existing one.

**Request body**

```json
{
  "message": "What have you been working on?",
  "session_id": "optional — omit to create new session"
}
```

**Response** `text/event-stream`

```
id: 1
data: {"type": "session", "session_id": "66abc123..."}

id: 2
data: {"type": "delta", "content": "Based on my recent activity,"}

id: 3
data: {"type": "delta", "content": " I deployed version 2.3.0 to staging."}

id: N
data: {"type": "done", "usage": {"prompt_tokens": 520, "completion_tokens": 140}, "message_id": "66def456..."}
```

**SSE event types**

| Type | When | Payload fields |
|------|------|----------------|
| `session` | First event | `session_id` |
| `delta` | Each token chunk | `content` |
| `done` | Stream complete | `usage`, `message_id` |
| `error` | Provider failure | `message` |

**Status codes**

| Code | Meaning |
|------|---------|
| 200 | Stream started |
| 400 | Session belongs to a different agent |
| 401 | Missing or invalid token |
| 403 | Not your session |
| 404 | Agent or session not found |

---

### GET `/api/agents/{agent_id}/chat/sessions`

List all chat sessions for an agent (newest first, paginated).

**Query parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `skip` | int | 0 | Offset for pagination |
| `limit` | int | 20 | Max sessions to return |

**Response** `200 OK`

```json
[
  {
    "id": "66abc123...",
    "agent_id": "66aaa111...",
    "title": "What have you been working on?",
    "message_count": 6,
    "created_at": "2026-04-17T10:00:00Z",
    "updated_at": "2026-04-17T10:05:00Z"
  }
]
```

---

### GET `/api/agents/{agent_id}/chat/sessions/{session_id}`

Get full session detail including all messages in chronological order.

**Response** `200 OK`

```json
{
  "id": "66abc123...",
  "agent_id": "66aaa111...",
  "title": "What have you been working on?",
  "message_count": 4,
  "created_at": "2026-04-17T10:00:00Z",
  "updated_at": "2026-04-17T10:03:00Z",
  "messages": [
    {
      "id": "66bbb222...",
      "role": "user",
      "content": "What have you been working on?",
      "usage": null,
      "created_at": "2026-04-17T10:00:00Z"
    },
    {
      "id": "66ccc333...",
      "role": "assistant",
      "content": "Based on my recent activity, I deployed version 2.3.0 to staging.",
      "usage": {"prompt_tokens": 520, "completion_tokens": 140},
      "created_at": "2026-04-17T10:00:03Z"
    }
  ]
}
```

---

### DELETE `/api/agents/{agent_id}/chat/sessions/{session_id}`

Delete a chat session and all its messages.

**Response** `204 No Content`

---

## Example: Full Chat Flow

```bash
# 1. Start a new session — note the session_id in the SSE response
curl -N -X POST http://localhost:8000/api/agents/AGENT_ID/chat \
  -H "Authorization: Bearer ghp_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "What skills do you have?"}'

# 2. Continue the conversation
curl -N -X POST http://localhost:8000/api/agents/AGENT_ID/chat \
  -H "Authorization: Bearer ghp_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "Can you explain the Kubernetes skill?", "session_id": "SESSION_ID"}'

# 3. List your sessions
curl http://localhost:8000/api/agents/AGENT_ID/chat/sessions \
  -H "Authorization: Bearer ghp_..."

# 4. Delete a session
curl -X DELETE http://localhost:8000/api/agents/AGENT_ID/chat/sessions/SESSION_ID \
  -H "Authorization: Bearer ghp_..."
```
