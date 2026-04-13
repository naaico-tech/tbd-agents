```
 █████╗ ██████╗  ██████╗██╗  ██╗██╗████████╗███████╗ ██████╗████████╗██╗   ██╗██████╗ ███████╗
██╔══██╗██╔══██╗██╔════╝██║  ██║██║╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██║   ██║██╔══██╗██╔════╝
███████║██████╔╝██║     ███████║██║   ██║   █████╗  ██║        ██║   ██║   ██║██████╔╝█████╗
██╔══██║██╔══██╗██║     ██╔══██║██║   ██║   ██╔══╝  ██║        ██║   ██║   ██║██╔══██╗██╔══╝
██║  ██║██║  ██║╚██████╗██║  ██║██║   ██║   ███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║███████╗
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝   ╚═╝   ╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝
```

<p align="center"><sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub></p>

> 🏛️ TBD Agent is a distributed system designed to run custom AI agents at scale. This document covers the system design, how requests flow through the stack, and how horizontal scaling works.>
> **New here?** Start with [Local Setup](local-setup.md) to get the system running first, then come back here to understand how the pieces connect.
---

## 🗺️ High-Level Overview

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║  ┌──────────────────────────────────────────────────────────────────┐   ║
║  │  👾 Clients (Dashboard / curl / CI pipelines / apps)            │   ║
║  │  Authorization: Bearer <GitHub PAT>                              │   ║
║  └──────────────────┬───────────────────────────────────────────────┘   ║
║                     │ HTTP                                             ║
║            ┌────────▼─────────┐                                        ║
║            │  ⚡ FastAPI (app) │──── GET /stream ──── SSE to client     ║
║            │   Port 8000      │                         ▲              ║
║            └──┬────────────┬──┘                         │              ║
║               │            │                            │ Redis Pub/Sub║
║               │ POST       │ Subscribe                  │              ║
║               │ /prompt    │                            │              ║
║               ▼            ▼                            │              ║
║         ┌──────────┐  ┌───────────┐              ┌─────┴──────┐       ║
║         │ 🗄 Mongo  │  │ 📡 Redis  │◄── Publish ──│ 🔧 Celery  │       ║
║         │  (state)  │  │ (broker + │              │  Workers   │       ║
║         │           │  │  pub/sub) │── Tasks ────►│  (N × M)   │       ║
║         └──────────┘  └───────────┘              └─────┬──────┘       ║
║                                                        │               ║
║                                                        │ SDK Session   ║
║                                                        ▼               ║
║                                               ┌─────────────────┐      ║
║                                               │ 🤖 Copilot SDK  │      ║
║                                               │ (JSON-RPC CLI)  │      ║
║                                               └──┬───────────┬──┘      ║
║                                                  │           │         ║
║                                                  ▼           ▼         ║
║                                           Copilot API    MCP Servers   ║
║                                          (Models API)   (stdio/SSE)    ║
║                                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## 🧱 Components

### ⚡ FastAPI API (`app` service)

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ THE GATEWAY ░░  ·  Handles HTTP, guards the gates      │
└─────────────────────────────────────────────────────────────┘
```

The API layer handles authentication, CRUD for agents/skills/MCP servers/workflows, and SSE streaming. It does **not** run agent logic — that's dispatched to workers.

- 🔹 **Endpoints** serve REST requests and validate GitHub PAT tokens
- 🔹 **SSE endpoint** (`GET /api/workflows/{id}/stream`) subscribes to a Redis pub/sub channel and streams events to the client in real-time
- 🔹 **Prompt dispatch** — `POST /api/workflows/{id}/prompt` enqueues a Celery task and returns `201` immediately

### 🔧 Celery Workers (`worker` service)

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ THE MUSCLE ░░  ·  Where agents actually do the work     │
└─────────────────────────────────────────────────────────────┘
```

Workers execute the actual agent loop. Each worker:

1. ► Receives a task from the Redis queue containing `(workflow_id, prompt, github_token)`
2. ► Initialises its own MongoDB connection via Beanie/Motor
3. ► Loads the Workflow, Agent, MCP servers, and Skills from the database
4. ► Creates a Copilot SDK session with the agent's configuration
5. ► Runs the SDK agentic loop — the SDK handles planning, tool calls, and response generation
6. ► Publishes real-time events (logs, message deltas, usage stats, status changes) to Redis pub/sub
7. ► Persists final state (messages, logs, usage, status) to MongoDB

**Key Celery settings:**

```
 ┌────────────────────────────┬─────────┬──────────────────────────────────────────────┐
 │  ░░ SETTING                │  VALUE  │  ░░ WHY                                      │
 ├────────────────────────────┼─────────┼──────────────────────────────────────────────┤
 │  worker_prefetch_multiplier│    1    │  Agent tasks are long-running; don't hoard   │
 │  task_acks_late            │  True   │  Re-queue tasks if a worker crashes          │
 │  task_reject_on_worker_lost│  True   │  Return tasks to the queue on shutdown       │
 └────────────────────────────┴─────────┴──────────────────────────────────────────────┘
```

### 📡 Redis

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ THE NERVOUS SYSTEM ░░  ·  Two roles, one service        │
└─────────────────────────────────────────────────────────────┘
```

Redis serves two roles:

1. **Celery broker/backend** — task queue for dispatching agent work and storing task results
2. **Event bus (pub/sub)** — workers publish events to `workflow:events:{id}` channels; the FastAPI SSE endpoint subscribes and relays events to clients

This decoupling is what enables multi-process and multi-node scaling — any worker can publish events that any API instance can stream.

### 🗄️ MongoDB

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ THE MEMORY BANK ░░  ·  All persistent state lives here  │
└─────────────────────────────────────────────────────────────┘
```

Stores all persistent state:

- 🤖 **Agents** — name, system prompt, model, MCP server IDs, MCP server tags
- 🔧 **MCP Servers** — name, transport type (stdio/SSE), connection config, tags, status
- 🧩 **Skills** — name, instructions, tags
- 📚 **Knowledge Bases** — name, description, tags
- 📄 **Knowledge Chunks** — content, pre-tokenised terms, source attribution
- ⚙️ **Workflows** — agent reference, model, max turns, session ID, status, messages, logs, usage stats

Each worker initialises its own Motor/Beanie connection on startup.

---

## 🎮 Request Flow: Sending a Prompt

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║  ►  1. Client  ──POST /prompt──────────────────────►  FastAPI          ║
║  ►  2. FastAPI ──validate auth + workflow state─────►  return 201      ║
║  ►  3. FastAPI ──run_agent_task.delay()─────────────►  Redis queue     ║
║  ►  4. Worker  ◄──picks up task from Redis queue                       ║
║  ►  5. Worker  ──init_db() + load Workflow from MongoDB                ║
║  ►  6. Worker  ──build_client(token) → SDK session                     ║
║  ►  7. Worker  ──session.send(prompt)                                  ║
║  ►  8. SDK     ──plans tool calls → MCP servers → generates response   ║
║  ►  9. Worker  ──on each event: Redis pub/sub + persist MongoDB        ║
║  ► 10. FastAPI ◄──SSE subscriber receives events                       ║
║  ► 11. Client  ◄──EventSource receives streamed events                 ║
║  ► 12. Worker  ──final state persisted, task complete ✓                ║
║                                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## 📈 Scaling

### ► Horizontal worker scaling

```bash
# Docker Compose — run 5 worker containers
docker-compose up --build --scale worker=5

# Each worker runs --concurrency=4, so total = 20 concurrent agent executions
```

Workers are stateless — they load everything from MongoDB and communicate via Redis. Add more containers to handle more concurrent agent runs.

### ► Horizontal API scaling

The FastAPI `app` service is also stateless. Run multiple instances behind a load balancer:

```bash
docker-compose up --build --scale app=3
```

SSE connections are per-client, and each API instance independently subscribes to Redis pub/sub for the relevant workflow channel.

### ► Infrastructure scaling

```
 ┌──────────────┬──────────────────────────────────────────────────────────┐
 │  ░░ COMPONENT│  ░░ SCALING STRATEGY                                    │
 ├──────────────┼──────────────────────────────────────────────────────────┤
 │  Redis       │  Redis Sentinel or Redis Cluster for HA                 │
 │  MongoDB     │  Replica sets or MongoDB Atlas                          │
 │  Workers     │  Increase --concurrency per container or add containers │
 │  API         │  Multiple instances behind a reverse proxy              │
 └──────────────┴──────────────────────────────────────────────────────────┘
```

---

## 🗃️ Data Model

```
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║  🤖 Agent                                                 ║
║  ├── name, description, system_prompt                     ║
║  ├── model (e.g. "gpt-4.1")                              ║
║  ├── mcp_server_ids[] ──► McpServer                       ║
║  └── mcp_server_tags[] (tag-based MCP resolution)         ║
║                                                           ║
║  🔧 McpServer                                             ║
║  ├── name, transport_type (stdio | sse)                   ║
║  ├── connection_config (command/args/env or url/headers)   ║
║  ├── tags[]                                               ║
║  └── status (registered | connected | error)              ║
║                                                           ║
║  🧩 Skill                                                 ║
║  ├── name, description, instructions                      ║
║  └── tags[]                                               ║
║                                                           ║
║  📚 KnowledgeBase                                         ║
║  ├── name, description                                    ║
║  └── tags[]                                               ║
║                                                           ║
║  📄 KnowledgeChunk                                        ║
║  ├── knowledge_base_id ──► KnowledgeBase                  ║
║  ├── content, tokens[] (BM25 pre-tokenised)               ║
║  └── source (attribution label)                           ║
║                                                           ║
║  ⚙️ Workflow                                               ║
║  ├── agent_id ──► Agent                                   ║
║  ├── model, max_turns, current_turn                       ║
║  ├── status (active|running|completed|failed|max_turns)   ║
║  ├── output_format (json | markdown)                      ║
║  ├── infinite_session (bool)                              ║
║  ├── usage { premium_req, in_tok, out_tok, cache, cost }  ║
║  ├── skill_ids[] ──► Skill                                ║
║  ├── knowledge_base_ids[] ──► KnowledgeBase               ║
║  ├── messages[] { role, content, tool_calls }             ║
║  └── logs[] { timestamp, event, detail }                  ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
```

---

## 📡 Event Bus Protocol

Events published to Redis channel `workflow:events:{workflow_id}`:

```json
{
  "type": "log | message | message_delta | usage | status",
  "data": { "..." },
  "timestamp": "2026-04-10T12:00:00+00:00"
}
```

```
 ┌─────────────────┬──────────────────────────────────┬─────────────────────────────────┐
 │  ░░ EVENT TYPE  │  ░░ PAYLOAD                      │  ░░ DESCRIPTION                 │
 ├─────────────────┼──────────────────────────────────┼─────────────────────────────────┤
 │  log            │  {event, detail}                 │  Agent lifecycle events          │
 │  message        │  {role, content}                 │  Complete assistant/tool message  │
 │  message_delta  │  {delta}                         │  Streaming token fragment         │
 │  usage          │  {total_in, total_out, cost...}  │  Cumulative usage stats           │
 │  status         │  {status, current_turn}          │  Workflow state changes           │
 └─────────────────┴──────────────────────────────────┴─────────────────────────────────┘
```

The frontend's `EventSource` connects to `GET /api/workflows/{id}/stream` and processes these events to render real-time logs, streaming responses, and usage metrics.

---

<p align="center">⬛⬜⬛ <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⬛⬜⬛</p>
