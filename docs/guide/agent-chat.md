# Agent Chat

Agent Chat lets you talk conversationally with a selected agent without creating a workflow task.

## Current Flutter UI

The Chat page exposes:

- an agent dropdown
- a current in-memory conversation per selected agent
- streaming assistant messages
- a **Clear conversation** action that resets the local session ID and message list

The current Flutter page does not expose persisted session list/history/delete controls. Those session endpoints exist in the API for clients that need them.

## Behavior

Chat assembles context from the agent profile, skills, available tools, recent task history, and memory. It streams responses over SSE and persists messages on the backend when a `session_id` is used or created.

```bash
curl -N -X POST http://localhost:8000/api/agents/<AGENT_ID>/chat \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What can you do?"}'
```

Use Chat for Q&A and agent self-awareness. Use [Run Task](tasks.md) when you need asynchronous task execution, tools, task history, or stop controls.

!!! note "Implementation note"
    Historical implementation planning is kept in [Agent Chat Plan](../agent-chat-plan.md) for reference; the guide above reflects current user-facing behavior.
