# Data Model

All persistent state is stored in MongoDB using Beanie ODM (async MongoDB object-document mapper built on Motor).

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
        bool caveman
        dict usage
        list skill_ids
        list messages
        list logs
    }

    KnowledgeSource {
        string id PK
        string name
        string type
        dict connection_config
        list tags
    }

    KnowledgeItem {
        string id PK
        string source_id FK
        string content
        string content_type
        list tags
    }

    Guardrail {
        string id PK
        string name
        string description
        string type
        dict config
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
| `caveman` | bool | Enable terse output + compressed injected context |
| `usage` | object | `{premium_req, in_tok, out_tok, cache_read, cache_write, cost}` |
| `skill_ids` | string[] | Installed skills |
| `messages` | array | `{role, content, tool_calls}` |
| `logs` | array | `{timestamp, event, detail}` |

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
