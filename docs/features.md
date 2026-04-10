# Features

A deep dive into what TBD Agent offers and how each capability works.

---

## Custom Agents

Agents are the core building block. Each agent encapsulates:

- **System prompt** — defines the agent's personality, domain expertise, and behavioural constraints
- **Model** — which Copilot-supported model to use (e.g. `gpt-4.1`, `o3-mini`, `claude-sonnet-4.5`)
- **MCP servers** — which tool servers the agent has access to

Create as many agents as you need — a code reviewer, an incident responder, a documentation writer — each with their own configuration. Agents are reusable across workflows.

```bash
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "incident-responder",
    "system_prompt": "You are an SRE investigating production incidents. Use Datadog to gather metrics and logs, then create a Jira ticket with your findings.",
    "model": "gpt-4.1",
    "mcp_server_ids": ["<DATADOG_MCP_ID>", "<JIRA_MCP_ID>"]
  }'
```

---

## MCP Tool Integration

TBD Agent supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) — the open standard for connecting AI models to external tools.

### Supported transports

| Transport | How it works | Example |
|---|---|---|
| **stdio** | Spawns a local process via `npx` or a binary; communicates over stdin/stdout | Datadog, Jira, GitHub, filesystem |
| **SSE** | Connects to a remote HTTP server via Server-Sent Events | Custom tool servers, remote APIs |

### Registering an MCP server

```bash
# stdio-based
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
    }
  }'

# SSE-based
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "custom-tools",
    "transport_type": "sse",
    "connection_config": {
      "url": "http://my-tool-server:3000/sse",
      "headers": {"Authorization": "Bearer secret"}
    }
  }'
```

### Auto-injected MCPs

When a workflow has **output destinations** configured (Notion or Slack), TBD Agent automatically injects the corresponding MCP servers into the session. The agent decides autonomously whether and when to use them based on its system prompt and the task at hand.

---

## Skills

Skills are reusable instruction modules that get injected into the system prompt at runtime. They let you shape agent behaviour without editing the agent's core prompt.

- Each skill has a **name**, **instructions** (free-text), and **tags**
- Skills are installed per-workflow, not per-agent — so the same agent can behave differently in different contexts

```bash
# Create a skill
curl -X POST http://localhost:8000/api/skills \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rca-format",
    "description": "Structures output as a Root Cause Analysis report",
    "instructions": "Structure your final output as an RCA report with sections: Summary, Timeline, Root Cause, Impact, Remediation, Prevention.",
    "tags": ["incident", "reporting"]
  }'

# Install it into a workflow
curl -X POST http://localhost:8000/api/workflows/<WF_ID>/skills/<SKILL_ID> \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

---

## Workflows

A workflow ties an agent to a specific execution context:

- **Agent** — which agent to use
- **Model override** — optionally use a different model than the agent's default
- **Max turns** — limit on tool-call rounds (prevents runaway loops)
- **Output format** — `json` or `markdown`
- **Infinite session** — enable/disable automatic context compaction
- **Output destinations** — optional Notion/Slack targets
- **Skills** — installed instruction modules

Workflows persist their full state: messages, logs, usage stats, and status.

---

## Real-Time Streaming (SSE)

When a prompt is sent, the agent runs on a Celery worker and publishes events to Redis. The API's SSE endpoint relays these events to any connected client.

### Event types

| Event | What it contains |
|---|---|
| `log` | Agent lifecycle events — tool calls, errors, compaction, session start/end |
| `message` | Complete assistant or tool message |
| `message_delta` | Streaming token — arrives character-by-character for live response rendering |
| `usage` | Cumulative token counts, premium requests, and cost |
| `status` | Workflow state changes (running → completed, failed, max_turns_reached) |

### Connecting

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

## Infinite Sessions

Long-running agents can exhaust a model's context window. TBD Agent uses the Copilot SDK's **infinite session** feature to handle this automatically:

- When the context fills to **80%**, background compaction starts — the SDK summarises older context to free space
- At **95%**, buffer exhaustion mode kicks in for aggressive compaction
- The agent continues working without interruption

This is enabled by default on new workflows and can be toggled off.

---

## Usage & Cost Tracking

Every workflow tracks cumulative usage data from the Copilot SDK:

| Metric | Description |
|---|---|
| `total_premium_requests` | Number of premium requests consumed |
| `total_input_tokens` | Total input tokens sent to the model |
| `total_output_tokens` | Total output tokens generated |
| `total_cache_read_tokens` | Tokens read from prompt cache |
| `total_cache_write_tokens` | Tokens written to prompt cache |
| `total_cost` | Estimated cost in USD |

Usage is published in real-time via SSE and persisted to the workflow document in MongoDB. The dashboard displays these metrics live during execution.

---

## Hooks & Error Recovery

The agent engine uses the Copilot SDK's hooks system for fine-grained control:

| Hook | Behaviour |
|---|---|
| `on_pre_tool_use` | Logs tool invocation; denies call if max turns exceeded |
| `on_post_tool_use` | Logs result; injects goal reminder when past 50% of max turns (reduces hallucination) |
| `on_error_occurred` | Retries recoverable errors up to 2×, then aborts |
| `on_session_end` | Logs session end reason |

The **permission handler** enforces max turns by counting tool calls and returning `denied-by-rules` when the limit is exceeded.

---

## Output Destinations

Workflows can optionally specify where the agent should send its output:

- **Notion** — provide a `notion_base_page_id`; the agent creates sub-pages under it
- **Slack** — provide a `slack_channel_id` or `slack_user_id`; the agent posts messages there

The agent decides autonomously when to use these destinations based on the task. Output destination hints are injected into the system prompt, and the corresponding MCP servers are auto-configured with the tokens from environment variables (`NOTION_TOKEN`, `SLACK_BOT_TOKEN`).

```json
{
  "output_destination": {
    "notion_base_page_id": "abc123-def456",
    "slack_channel_id": "C01ABCDEF"
  }
}
```

---

## Dashboard

TBD Agent ships with a built-in single-page dashboard at `/dashboard` that provides:

- **Overview** — agent, MCP server, skill, and workflow counts
- **Agent management** — create, edit, delete agents; assign MCP servers
- **MCP management** — register servers, test connections
- **Skill management** — create and manage instruction modules
- **Workflow management** — create workflows with infinite session and output destination settings
- **Run Task** — select a workflow, type a prompt, and watch the agent work in real-time with streaming logs, token-by-token responses, and live usage metrics

---

## Distributed Execution

TBD Agent separates the API layer from agent execution via Celery + Redis:

- The **API** handles HTTP requests and SSE streaming — lightweight and fast
- **Workers** handle the heavy lifting — SDK sessions, tool calls, model inference
- **Redis** bridges them — task queue for dispatch, pub/sub for real-time events

This means:
- **Scale workers independently** — add containers or increase concurrency based on workload
- **API stays responsive** — prompt dispatch is instant; no blocking on agent execution
- **Fault tolerance** — if a worker crashes, `task_acks_late` re-queues the task; the workflow is marked as failed
- **Multi-node** — workers can run on different machines, all connecting to the same Redis and MongoDB

See [architecture.md](architecture.md) for the full system diagram and scaling guide.
