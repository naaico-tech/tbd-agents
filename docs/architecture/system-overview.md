# System Overview

TBD Agents separates concerns across four main components connected by Redis and MongoDB.

---

## High-Level Architecture

```mermaid
graph TB
    subgraph Clients
        Dashboard([Dashboard])
        CLI([curl / CLI])
        Apps([Applications])
    end

    subgraph API Layer
        FastAPI[FastAPI API<br/>Port 8000]
    end

    subgraph Message Broker
        Redis[(Redis<br/>Broker + Pub/Sub)]
    end

    subgraph Worker Pool
        W1[Worker 1]
        W2[Worker 2]
        W3[Worker N]
    end

    subgraph External
        SDK[Copilot SDK<br/>JSON-RPC CLI]
        Models[Copilot Models API]
        MCP1[MCP Server: Jira]
        MCP2[MCP Server: Datadog]
        MCPN[MCP Server: ...]
    end

    subgraph Storage
        Mongo[(MongoDB)]
    end

    Dashboard & CLI & Apps -->|HTTP + Auth| FastAPI
    FastAPI -->|Enqueue Tasks| Redis
    FastAPI -->|Subscribe Events| Redis
    FastAPI -->|SSE Stream| Dashboard & CLI & Apps
    FastAPI -->|Read/Write| Mongo

    Redis -->|Deliver Tasks| W1 & W2 & W3
    W1 & W2 & W3 -->|Publish Events| Redis
    W1 & W2 & W3 -->|Persist State| Mongo
    W1 & W2 & W3 -->|SDK Session| SDK

    SDK --> Models
    SDK --> MCP1 & MCP2 & MCPN
```

---

## Components

### FastAPI API

The API layer handles authentication, CRUD for agents/skills/MCP servers/workflows, and SSE streaming. It does **not** run agent logic — that's dispatched to workers.

- **Endpoints** serve REST requests and validate GitHub PAT tokens
- **SSE endpoint** (`GET /api/workflows/{id}/stream`) subscribes to a Redis pub/sub channel and streams events to the client
- **Prompt dispatch** — `POST /api/workflows/{id}/prompt` enqueues a Celery task and returns `201` immediately

### Celery Workers

Workers execute the actual agent loop. Each worker:

1. Receives a task from the Redis queue containing `(workflow_id, prompt, github_token)`
2. Initialises its own MongoDB connection via Beanie/Motor
3. Loads the Workflow, Agent, MCP servers, and Skills from the database
4. Creates a Copilot SDK session with the agent's configuration
5. Runs the SDK agentic loop — the SDK handles planning, tool calls, and response generation
6. Publishes real-time events (logs, message deltas, usage stats, status changes) to Redis pub/sub
7. Persists final state (messages, logs, usage, status) to MongoDB

**Key Celery settings:**

| Setting | Value | Why |
|---|---|---|
| `worker_prefetch_multiplier` | `1` | Agent tasks are long-running; don't hoard |
| `task_acks_late` | `True` | Re-queue tasks if a worker crashes |
| `task_reject_on_worker_lost` | `True` | Return tasks to the queue on shutdown |

### Redis

Redis serves two roles:

1. **Celery broker/backend** — task queue for dispatching agent work and storing task results
2. **Event bus (pub/sub)** — workers publish events to `workflow:events:{id}` channels; the FastAPI SSE endpoint subscribes and relays events to clients

This decoupling enables multi-process and multi-node scaling — any worker can publish events that any API instance can stream.

### MongoDB

Stores all persistent state: agents, MCP servers, skills, workflows (including messages, logs, and usage stats). Each worker initialises its own Motor/Beanie connection on startup.

---

## Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI API
    participant Redis
    participant Worker as Celery Worker
    participant SDK as Copilot SDK
    participant MCP as MCP Servers
    participant Mongo as MongoDB

    Client->>API: POST /prompt (auth + payload)
    API->>API: Validate auth + workflow state
    API-->>Client: 201 Accepted
    API->>Redis: run_agent_task.delay()

    Client->>API: GET /stream (SSE)

    Redis->>Worker: Deliver task
    Worker->>Mongo: Load Workflow + Agent + MCPs + Skills
    Worker->>SDK: build_client(token) → session
    Worker->>SDK: session.send(prompt)

    loop Agent Loop
        SDK->>MCP: Tool calls
        MCP-->>SDK: Tool results
        SDK->>Worker: Events (deltas, usage, logs)
        Worker->>Redis: Publish to channel
        Redis->>API: Event delivered
        API-->>Client: SSE event
    end

    Worker->>Mongo: Persist final state
    Worker->>Redis: Publish status: completed
    Redis->>API: Final event
    API-->>Client: SSE: status completed
```

---

## Event Bus Protocol

Events published to Redis channel `workflow:events:{workflow_id}`:

```json
{
  "type": "log | message | message_delta | usage | status",
  "data": { "..." },
  "timestamp": "2026-04-10T12:00:00+00:00"
}
```

| Event Type | Payload | Description |
|---|---|---|
| `log` | `{event, detail}` | Agent lifecycle events |
| `message` | `{role, content}` | Complete assistant/tool message |
| `message_delta` | `{delta}` | Streaming token fragment |
| `usage` | `{total_in, total_out, cost...}` | Cumulative usage stats |
| `status` | `{status, current_turn}` | Workflow state changes |

---

## Hooks & Error Recovery

The agent engine uses the Copilot SDK's hooks system for fine-grained control:

| Hook | Behaviour |
|---|---|
| `on_pre_tool_use` | Logs tool invocation; denies if max turns exceeded |
| `on_post_tool_use` | Logs result; injects goal reminder past 50% turns |
| `on_error_occurred` | Retries recoverable errors up to 2×, then aborts |
| `on_session_end` | Logs session end reason |

The **permission handler** enforces max turns by counting tool calls and returning `denied-by-rules` when the limit is exceeded.
