# Data Model

Persistent state is stored in the configured document backend: MongoDB/Beanie by default (`DB_BACKEND=mongo`) or PostgreSQL JSONB tables when `DB_BACKEND=postgres`. The logical entities are the same across both backends.

---

## Entity Relationship Diagram

```mermaid
erDiagram
    Agent {
        string id PK
        string name
        string description
        string system_prompt
        string model
        list mcp_server_ids
        list mcp_server_tags
        list custom_tool_ids
        list builtin_tools
        list knowledge_source_ids
        list knowledge_tags
        string provider_id
    }

    McpServer {
        string id PK
        string name
        string transport_type
        dict connection_config
        list tags
        string status
    }

    Skill {
        string id PK
        string name
        string description
        string instructions
        list tags
    }

    Workflow {
        string id PK
        string agent_id FK
        string model
        int max_turns
        int current_turn
        string status
        string output_format
        bool infinite_session
        bool bypass_memory
        bool auto_memory
        string reasoning_effort
        bool caveman
        dict usage
        list skill_ids
        list messages
        list logs
    }

    KnowledgeSource {
        string id PK
        string name
        string source_type
        dict connection_config
        list tags
    }

    KnowledgeItem {
        string id PK
        string source_id FK
        string text_content
        string content_type
        list tags
    }

    Guardrail {
        string id PK
        string name
        string description
        string guardrail_type
        dict prompt_config
        dict request_config
        dict output_config
    }

    ScheduledAgent {
        string id PK
        string workflow_id FK
        string prompt
        int interval_value
        string interval_unit
        bool enabled
    }

    Provider {
        string id PK
        string name
        dict config
    }

    Token {
        string id PK
        string name
        string encrypted_value
    }

    TaskExecution {
        string id PK
        string workflow_id FK
        string status
        string error
        datetime created_at
        datetime completed_at
    }

    Agent ||--o{ Workflow : "used by"
    Agent }o--o{ McpServer : "mcp_server_ids"
    Workflow }o--o{ Skill : "skill_ids"
    Workflow ||--o{ TaskExecution : "executions"
    Workflow ||--o{ ScheduledAgent : "scheduled by"
    KnowledgeSource ||--o{ KnowledgeItem : "contains"
```

---

## Core Entities

### Agent

The reusable definition of an AI agent — personality, model, and tool access.

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique agent name |
| `description` | string | Optional description |
| `system_prompt` | string | Defines agent behaviour |
| `model` | string | Copilot model (e.g. `gpt-4.1`) |
| `mcp_server_ids` | string[] | Explicit MCP server references |
| `mcp_server_tags` | string[] | Tag-based MCP resolution |
| `custom_tool_ids` | string[] | Custom Python tools mounted on the agent |
| `builtin_tools` | string[] | Built-in tools such as `bash`, `read`, `grep`, `web_fetch` |
| `provider_id` | string | Optional BYOK provider |
| `knowledge_source_ids` | string[] | Explicit knowledge sources |
| `knowledge_tags` | string[] | Tag-based knowledge matching |

### Workflow

An execution context that ties an agent to a conversation session.

| Field | Type | Description |
|---|---|---|
| `agent_id` | string | Reference to the agent |
| `model` | string | Optional model override |
| `max_turns` | int | Tool-call round limit |
| `current_turn` | int | Current turn counter |
| `status` | enum | `active` / `running` / `completed` / `failed` / `max_turns` |
| `output_format` | string | `json` or `markdown` |
| `infinite_session` | bool | Enable context compaction |
| `bypass_memory` | bool | Skip memory context injection |
| `auto_memory` | bool | Enable automatic memory extraction |
| `reasoning_effort` | string | Optional `low` / `medium` / `high` effort hint |
| `caveman` | bool | Enable terse output + compressed injected context |
| `usage` | object | `{premium_req, in_tok, out_tok, cache_read, cache_write, cost}` |
| `skill_ids` | string[] | Installed skills |
| `messages` | array | `{role, content, tool_calls}` |
| `logs` | array | `{timestamp, event, detail}` |

Workflows can also reference `guardrail_ids`, `guardrail_tags`, `skill_tags`, repository checkout fields, credential overrides, and webhook/error webhook URLs.

### McpServer

A registered MCP tool server.

| Field | Type | Description |
|---|---|---|
| `name` | string | Server name |
| `transport_type` | enum | `stdio` or `sse` |
| `connection_config` | object | Transport-specific config |
| `tags` | string[] | Free-form labels |
| `status` | enum | `registered` / `connected` / `error` |

### Skill

A reusable instruction module.

| Field | Type | Description |
|---|---|---|
| `name` | string | Skill name |
| `description` | string | Human-readable description |
| `instructions` | string | Injected into system prompt at runtime |
| `tags` | string[] | Free-form labels |
