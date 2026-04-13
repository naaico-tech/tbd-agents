```
███████╗███████╗ █████╗ ████████╗██╗   ██╗██████╗ ███████╗███████╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██╔══██╗██╔════╝██╔════╝
█████╗  █████╗  ███████║   ██║   ██║   ██║██████╔╝█████╗  ███████╗
██╔══╝  ██╔══╝  ██╔══██║   ██║   ██║   ██║██╔══██╗██╔══╝  ╚════██║
██║     ███████╗██║  ██║   ██║   ╚██████╔╝██║  ██║███████╗███████║
╚═╝     ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝
```

<p align="center"><sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub></p>

> 🎮 A deep dive into what TBD Agent offers and how each capability works.
>
> **Prerequisites:** Make sure you have a running instance first — see [Local Setup](local-setup.md).

---

## 🤖 Custom Agents

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ PLAYER SELECT ░░  ·  Build your squad                   │
└─────────────────────────────────────────────────────────────┘
```

Agents are the core building block. Each agent encapsulates:

- 💬 **System prompt** — defines the agent's personality, domain expertise, and behavioural constraints
- 🧠 **Model** — which Copilot-supported model to use (e.g. `gpt-4.1`, `o3-mini`, `claude-sonnet-4.5`)
- 🔧 **MCP servers** — which tool servers the agent has access to (by ID or tags)

Create as many agents as you need — a code reviewer, an incident responder, a documentation writer — each with their own configuration. Agents are reusable across workflows.

```bash
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "incident-responder",
    "system_prompt": "You are an SRE investigating production incidents. Use Datadog to gather metrics and logs, then create a Jira ticket with your findings.",
    "model": "gpt-4.1",
    "mcp_server_ids": ["<DATADOG_MCP_ID>", "<JIRA_MCP_ID>"],
    "mcp_server_tags": ["observability", "ticketing"]
  }'
```

---

## 🔧 MCP Tool Integration

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ EQUIP ITEMS ░░  ·  Power up with external tools         │
└─────────────────────────────────────────────────────────────┘
```

TBD Agent supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) — the open standard for connecting AI models to external tools.

### ► Supported transports

```
 ┌─────────────┬────────────────────────────────────────────────────────────────┐
 │  ░░ TYPE    │  ░░ HOW IT WORKS                                              │
 ├─────────────┼────────────────────────────────────────────────────────────────┤
 │  stdio      │  Spawns a local process via npx; communicates over stdin/out  │
 │  SSE        │  Connects to a remote HTTP server via Server-Sent Events      │
 └─────────────┴────────────────────────────────────────────────────────────────┘
```

### ► Registering an MCP server

```bash
# ▓▓ stdio-based ▓▓
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "jira",
    "transport_type": "stdio",
    "connection_config": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-atlassian"],
      "env": {"ATLASSIAN_API_TOKEN": "...", "ATLASSIAN_EMAIL": "...", "ATLASSIAN_URL": "..."}
    },
    "tags": ["ticketing", "project-management"]
  }'

# ▓▓ SSE-based ▓▓
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "custom-tools",
    "transport_type": "sse",
    "connection_config": {
      "url": "http://my-tool-server:3000/sse",
      "headers": {"Authorization": "Bearer secret"}
    },
    "tags": ["internal"]
  }'
```

### ► MCP Tags

Every MCP server can have **tags** — free-form labels that categorise the server by domain or function (e.g. `observability`, `ticketing`, `documentation`, `messaging`).

Agents select which MCP servers to use in two ways:

- 🏷️ **By ID** — explicit `mcp_server_ids` list for known servers
- 🏷️ **By tag** — `mcp_server_tags` list; any MCP server matching at least one tag is included

Both are unioned at runtime with deduplication, so an MCP server that matches both by ID and by tag is only loaded once. This is how you support different "flavors of work" — tag your Notion MCP as `documentation`, your Slack MCP as `messaging`, your Datadog MCP as `observability`, and then agents pick up the right tools by declaring the categories they need.

---

## 🧩 Skills

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SKILL TREE ░░  ·  Upgrade your agent's abilities        │
└─────────────────────────────────────────────────────────────┘
```

Skills are reusable instruction modules that get injected into the system prompt at runtime. They let you shape agent behaviour without editing the agent's core prompt.

- Each skill has a **name**, **instructions** (free-text), and **tags**
- Skills are installed per-workflow, not per-agent — so the same agent can behave differently in different contexts

```bash
# ► Create a skill
curl -X POST http://localhost:8000/api/skills \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rca-format",
    "description": "Structures output as a Root Cause Analysis report",
    "instructions": "Structure your final output as an RCA report with sections: Summary, Timeline, Root Cause, Impact, Remediation, Prevention.",
    "tags": ["incident", "reporting"]
  }'

# ► Install it into a workflow
curl -X POST http://localhost:8000/api/workflows/<WF_ID>/skills/<SKILL_ID> \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

---

## 📚 Knowledge Bases

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ CODEX ░░  ·  Give your agent a searchable memory        │
└─────────────────────────────────────────────────────────────┘
```

Knowledge Bases let you store domain-specific documents (runbooks, API docs, policies, FAQs) in MongoDB and have the agent automatically retrieve the most relevant chunks at run time using **BM25 ranking** — no vector database required.

- Each knowledge base holds **named, tagged chunks** of text
- Chunks are **pre-tokenised on write** for fast BM25 scoring
- At run time, the top-5 most relevant chunks are injected into the system prompt as a `<knowledge_context>` block
- Knowledge bases are **shared across workflows** — attach as many KBs to a workflow as you need

```bash
# ► Create a knowledge base
curl -X POST http://localhost:8000/api/knowledge-bases \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "sre-runbooks", "description": "On-call runbooks", "tags": ["sre"]}'

# ► Add a chunk
curl -X POST http://localhost:8000/api/knowledge-bases/<KB_ID>/chunks \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "## DB Connection Exhaustion\nStep 1: Check pg_stat_activity...", "source": "runbooks/db.md"}'

# ► Attach to a workflow
curl -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "<AGENT_ID>", "knowledge_base_ids": ["<KB_ID>"]}'
```

See [knowledge-base.md](knowledge-base.md) for the full design report, API reference, chunking strategies, and vector-search upgrade path.

---

## ⚙️ Workflows

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ GAME SESSION ░░  ·  Where the action happens            │
└─────────────────────────────────────────────────────────────┘
```

A workflow ties an agent to a specific execution context:

- 🤖 **Agent** — which agent to use
- 🧠 **Model override** — optionally use a different model than the agent's default
- 🔄 **Max turns** — limit on tool-call rounds (prevents runaway loops)
- 📝 **Output format** — `json` or `markdown`
- ♾️ **Infinite session** — enable/disable automatic context compaction
- 🧩 **Skills** — installed instruction modules

Workflows persist their full state: messages, logs, usage stats, and status.

---

## ⚡ Real-Time Streaming (SSE)

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ LIVE FEED ░░  ·  Watch the magic unfold in real-time    │
└─────────────────────────────────────────────────────────────┘
```

When a prompt is sent, the agent runs on a Celery worker and publishes events to Redis. The API's SSE endpoint relays these events to any connected client.

### ► Event types

```
 ┌─────────────────┬────────────────────────────────────────────────────────────┐
 │  ░░ EVENT       │  ░░ WHAT IT CONTAINS                                      │
 ├─────────────────┼────────────────────────────────────────────────────────────┤
 │  log            │  Agent lifecycle: tool calls, errors, compaction, etc.     │
 │  message        │  Complete assistant or tool message                        │
 │  message_delta  │  Streaming token — live character-by-character rendering   │
 │  usage          │  Cumulative token counts, premium requests, and cost       │
 │  status         │  Workflow state changes (running → completed/failed)       │
 └─────────────────┴────────────────────────────────────────────────────────────┘
```

### ► Connecting

```bash
# CLI
curl -N http://localhost:8000/api/workflows/<WF_ID>/stream

# JavaScript
const es = new EventSource('/api/workflows/<WF_ID>/stream');
es.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  // type: log | message | message_delta | usage | status
};
```

The built-in dashboard uses this SSE stream to render live logs, token-by-token message streaming, and real-time usage metrics.

---

## ♾️ Infinite Sessions

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ EXTRA LIVES ░░  ·  Your agent never runs out of memory  │
└─────────────────────────────────────────────────────────────┘
```

Long-running agents can exhaust a model's context window. TBD Agent uses the Copilot SDK's **infinite session** feature to handle this automatically:

- ► At **80%** context fill → background compaction starts (SDK summarises older context)
- ► At **95%** → buffer exhaustion mode kicks in for aggressive compaction
- ► The agent continues working without interruption ✓

This is enabled by default on new workflows and can be toggled off.

---

## 📊 Usage & Cost Tracking

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SCORE BOARD ░░  ·  Track every token and every penny    │
└─────────────────────────────────────────────────────────────┘
```

Every workflow tracks cumulative usage data from the Copilot SDK:

```
 ┌──────────────────────────┬──────────────────────────────────────────────┐
 │  ░░ METRIC               │  ░░ DESCRIPTION                              │
 ├──────────────────────────┼──────────────────────────────────────────────┤
 │  total_premium_requests   │  Number of premium requests consumed         │
 │  total_input_tokens       │  Total input tokens sent to the model        │
 │  total_output_tokens      │  Total output tokens generated               │
 │  total_cache_read_tokens  │  Tokens read from prompt cache               │
 │  total_cache_write_tokens │  Tokens written to prompt cache              │
 │  total_cost               │  Estimated cost in USD                       │
 └──────────────────────────┴──────────────────────────────────────────────┘
```

Usage is published in real-time via SSE and persisted to the workflow document in MongoDB. The dashboard displays these metrics live during execution.

---

## 🪝 Hooks & Error Recovery

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ CHEAT CODES ░░  ·  Fine-grained control over the loop   │
└─────────────────────────────────────────────────────────────┘
```

The agent engine uses the Copilot SDK's hooks system for fine-grained control:

```
 ┌─────────────────────┬────────────────────────────────────────────────────────┐
 │  ░░ HOOK            │  ░░ BEHAVIOUR                                          │
 ├─────────────────────┼────────────────────────────────────────────────────────┤
 │  on_pre_tool_use    │  Logs tool invocation; denies if max turns exceeded    │
 │  on_post_tool_use   │  Logs result; injects goal reminder past 50% turns    │
 │  on_error_occurred  │  Retries recoverable errors up to 2×, then aborts     │
 │  on_session_end     │  Logs session end reason                               │
 └─────────────────────┴────────────────────────────────────────────────────────┘
```

The **permission handler** enforces max turns by counting tool calls and returning `denied-by-rules` when the limit is exceeded.

---

## 🖥️ Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ HOME SCREEN ░░  ·  Your command center                  │
└─────────────────────────────────────────────────────────────┘
```

TBD Agent ships with a built-in single-page dashboard at `/dashboard` that provides:

- 📊 **Overview** — agent, MCP server, skill, and workflow counts
- 🤖 **Agent management** — create, edit, delete agents; assign MCP servers
- 🔧 **MCP management** — register servers, test connections
- 🧩 **Skill management** — create and manage instruction modules
- ⚙️ **Workflow management** — create workflows with infinite session settings
- ▶️ **Run Task** — select a workflow, type a prompt, and watch the agent work in real-time with streaming logs, token-by-token responses, and live usage metrics

---

## 🔀 Distributed Execution

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ MULTIPLAYER MODE ░░  ·  Scale across the cluster        │
└─────────────────────────────────────────────────────────────┘
```

TBD Agent separates the API layer from agent execution via Celery + Redis:

- The **API** handles HTTP requests and SSE streaming — lightweight and fast
- **Workers** handle the heavy lifting — SDK sessions, tool calls, model inference
- **Redis** bridges them — task queue for dispatch, pub/sub for real-time events

This means:

- ► **Scale workers independently** — add containers or increase concurrency based on workload
- ► **API stays responsive** — prompt dispatch is instant; no blocking on agent execution
- ► **Fault tolerance** — if a worker crashes, `task_acks_late` re-queues the task; the workflow is marked as failed
- ► **Multi-node** — workers can run on different machines, all connecting to the same Redis and MongoDB

See [architecture.md](architecture.md) for the full system diagram and scaling guide.

---

<p align="center">⬛⬜⬛ <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⬛⬜⬛</p>
