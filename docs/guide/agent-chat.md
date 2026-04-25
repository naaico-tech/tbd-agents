# Agent Chat

Talk to your agents conversationally — ask questions about their configuration,
capabilities, and recent work without triggering any task execution.

---

## Overview

The **Agent Chat** feature gives every agent a real-time, multi-turn chat interface.
Unlike the workflow prompt system (which dispatches Celery tasks and runs tools),
chat is a **pure conversational interface**:

- ✅ Answers questions about what the agent can do
- ✅ Describes its skills, tools, and memory
- ✅ Summarizes its recent task history
- ✅ Streams responses token-by-token via SSE
- ❌ Does **not** execute tools or trigger workflows

---

## What can I ask?

Any question about the agent's context — for example:

| Question | What the agent draws on |
|----------|------------------------|
| *"What have you been working on?"* | Recent task history |
| *"What tools do you have access to?"* | MCP server tools + built-in tools |
| *"What skills are you configured with?"* | Installed skill documents |
| *"What do you remember about the last deployment?"* | STM + LTM memories |
| *"What model are you using?"* | Agent profile / config |

---

## How it works

```
Client ──POST──► /api/agents/{id}/chat ──► ChatHandler (in-process)
  │                                              │
  │◄──── SSE token stream ◄─────────────────────┘
                                                 │
           ┌──────────────────────────┐          │
           │    Context Assembly      │◄─────────┘
           │  ① Agent profile         │
           │  ② Skills                │
           │  ③ Available tools       │
           │  ④ Recent task history   │
           │  ⑤ STM + LTM memories    │
           └──────────────────────────┘
```

On each message:

1. A `ChatSession` is created (or reused if you pass a `session_id`).
2. The agent's self-awareness context is assembled from its configuration.
3. Conversation history is loaded from MongoDB (last 50 messages).
4. The LLM is called **directly from the FastAPI process** — no Celery overhead.
5. Response tokens stream back via SSE.
6. User and assistant messages are persisted to MongoDB.

---

## Quick start

### Start a new conversation

```bash
curl -N -X POST http://localhost:8000/api/agents/AGENT_ID/chat \
  -H "Authorization: Bearer ghp_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "What can you do?"}'
```

You will receive an SSE stream:

```
id: 1
data: {"type": "session", "session_id": "66abc123..."}

id: 2
data: {"type": "delta", "content": "I am a deployment assistant"}

id: 3
data: {"type": "delta", "content": " configured with the following skills…"}

id: N
data: {"type": "done", "usage": {"prompt_tokens": 480, "completion_tokens": 95}, "message_id": "66def..."}
```

### Continue a conversation

```bash
curl -N -X POST http://localhost:8000/api/agents/AGENT_ID/chat \
  -H "Authorization: Bearer ghp_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "What was the last task you completed?", "session_id": "66abc123..."}'
```

### List your sessions

```bash
curl http://localhost:8000/api/agents/AGENT_ID/chat/sessions \
  -H "Authorization: Bearer ghp_..."
```

### View a session with full history

```bash
curl http://localhost:8000/api/agents/AGENT_ID/chat/sessions/SESSION_ID \
  -H "Authorization: Bearer ghp_..."
```

### Delete a session

```bash
curl -X DELETE http://localhost:8000/api/agents/AGENT_ID/chat/sessions/SESSION_ID \
  -H "Authorization: Bearer ghp_..."
```

---

## Conversation context

The agent is given an `<agent_context>` block at the start of every chat containing:

```xml
<agent_context>
  <agent_profile>
    <name>Deploy Assistant</name>
    <model>gpt-4o</model>
    <description>Handles deployment workflows</description>
  </agent_profile>

  <skills>
    <skill>
      <name>Kubernetes Deployments</name>
      <description>Manages k8s deployments and rollbacks</description>
    </skill>
  </skills>

  <available_tools>
    <tool>kubectl_apply</tool>
    <tool>git_push</tool>
    <tool>slack_notify</tool>
  </available_tools>

  <task_history>
    <task>
      <prompt>Deploy v2.3.0 to staging</prompt>
      <status>completed</status>
      <created_at>2026-04-17T10:00:00Z</created_at>
    </task>
  </task_history>

  <!-- STM/LTM memories from Redis + MongoDB -->
</agent_context>
```

---

## Session lifecycle

```
New message without session_id
        │
        ▼
   Create ChatSession
        │
        ▼
   handle_chat()
        │
        ├─► yield session event
        ├─► stream LLM response (delta events)
        └─► yield done event
                │
                ▼
        Persist user + assistant ChatMessages
        Update ChatSession (count, title, updated_at)
```

Sessions are automatically titled from the first message (truncated to 60 characters).

---

## Configuration

Chat inherits the agent's attached **BYOK provider** if configured. If no provider is
attached, the GitHub Models inference endpoint is used with the user's GitHub token.

| Setting | Default | Description |
|---------|---------|-------------|
| Conversation window | 50 messages | Older messages are dropped |
| Response timeout | 120 s | Per-response timeout |
| Session title | First 60 chars | Auto-generated from first message |
| Task history | Last 10 tasks | Summarised in context |

---

## Observability

Two new Prometheus metrics track chat activity:

| Metric | Labels | Description |
|--------|--------|-------------|
| `copilot_hub_chat_messages_total` | `role` | Messages processed (user / assistant) |
| `copilot_hub_chat_response_duration_seconds` | `model` | LLM response time histogram |

The existing `copilot_hub_sse_connections_active` gauge covers active chat SSE connections.
