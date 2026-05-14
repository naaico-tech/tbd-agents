---
icon: material/database-export
---

# Import & Export API

All import/export endpoints require an `Authorization: Bearer <GITHUB_TOKEN>` header.

---

## Bundle Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/export` | Export all resources (skills, agents, workflows, knowledge sources) |
| `POST` | `/api/import` | Import a full bundle |

---

## Per-Resource Endpoints

### Skills

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/skills/export` | Export all skills |
| `GET` | `/api/skills/{id}/export` | Export a single skill |
| `POST` | `/api/skills/import` | Bulk import skills |

### Agents

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/agents/export` | Export all agents |
| `GET` | `/api/agents/{id}/export` | Export a single agent |
| `POST` | `/api/agents/import` | Bulk import agents |

### Workflows

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/workflows/export` | Export the authenticated user's workflows |
| `GET` | `/api/workflows/{id}/export` | Export a single workflow |
| `POST` | `/api/workflows/import` | Bulk import workflows |

### Knowledge Sources

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/knowledge-sources/export` | Export all knowledge sources |
| `GET` | `/api/knowledge-sources/{id}/export` | Export a single knowledge source |
| `POST` | `/api/knowledge-sources/import` | Bulk import knowledge sources |

---

## Schemas

### `FullExportBundle` (request/response for `GET /api/export` and `POST /api/import`)

```json
{
  "version": "1.0",
  "exported_at": "2026-04-28T10:00:00+00:00",
  "resource_type": "bundle",
  "skills": [ /* ExportedSkill[] */ ],
  "agents": [ /* ExportedAgent[] */ ],
  "workflows": [ /* ExportedWorkflow[] */ ],
  "knowledge_sources": [ /* ExportedKnowledgeSource[] */ ]
}
```

### Per-Resource Export Bundle (e.g. `SkillExportBundle`)

```json
{
  "version": "1.0",
  "exported_at": "2026-04-28T10:00:00+00:00",
  "resource_type": "skill",
  "items": [ /* ExportedSkill[] */ ]
}
```

`resource_type` values: `"skill"` · `"agent"` · `"workflow"` · `"knowledge_source"`

### Per-Resource Import Body (e.g. `SkillImportBundle`)

```json
{
  "items": [ /* ExportedSkill[] */ ]
}
```

---

## Item Schemas

### `ExportedSkill`

```json
{
  "name": "rca-format",
  "description": "Structures output as a Root Cause Analysis report",
  "instructions": "Structure your final output as an RCA report.",
  "tags": ["incident", "reporting"]
}
```

| Field | Type | Required | Default |
|---|---|---|---|
| `name` | `string` | ✅ | — |
| `description` | `string` | | `""` |
| `instructions` | `string` | ✅ | — |
| `tags` | `string[]` | | `[]` |

---

### `ExportedAgent`

```json
{
  "name": "ops-agent",
  "description": "SRE operations assistant",
  "system_prompt": "You are an expert SRE assistant.",
  "model": "gpt-4o",
  "mcp_server_ids": [],
  "mcp_server_tags": [],
  "tool_definitions": [],
  "knowledge_source_ids": [],
  "knowledge_tags": [],
  "builtin_tools": [],
  "custom_tool_ids": [],
  "provider_id": null
}
```

| Field | Type | Required | Default |
|---|---|---|---|
| `name` | `string` | ✅ | — |
| `description` | `string` | | `""` |
| `system_prompt` | `string` | | `"You are a helpful assistant."` |
| `model` | `string \| null` | | `null` |
| `mcp_server_ids` | `string[]` | | `[]` |
| `mcp_server_tags` | `string[]` | | `[]` |
| `tool_definitions` | `object[]` | | `[]` |
| `knowledge_source_ids` | `string[]` | | `[]` |
| `knowledge_tags` | `string[]` | | `[]` |
| `builtin_tools` | `string[]` | | `[]` |
| `custom_tool_ids` | `string[]` | | `[]` |
| `provider_id` | `string \| null` | | `null` |

---

### `ExportedWorkflow`

```json
{
  "title": "Incident Response",
  "agent_id": "664f1a2b3c4d5e6f7a8b9c0d",
  "model": "gpt-4o",
  "max_turns": 5,
  "skill_ids": [],
  "skill_tags": [],
  "output_format": "json",
  "infinite_session": true,
  "caveman": false,
  "bypass_memory": false,
  "auto_memory": false,
  "tsv_tool_results": false,
  "reasoning_effort": null,
  "guardrail_ids": [],
  "guardrail_tags": [],
  "repo_url": null,
  "repo_branch": null,
  "repo_token_name": null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `agent_id` | `string` | ✅ | Must reference an existing agent in the target system |
| `model` | `string` | ✅ | — |
| `title` | `string \| null` | | — |
| `max_turns` | `integer` | | Default `5` |
| `skill_ids` | `string[]` | | — |
| `skill_tags` | `string[]` | | — |
| `output_format` | `string` | | Default `"json"` |
| `infinite_session` | `boolean` | | Default `true` |
| `guardrail_ids` | `string[]` | | — |
| `guardrail_tags` | `string[]` | | — |
| `repo_url` | `string \| null` | | — |
| `repo_branch` | `string \| null` | | — |
| `repo_token_name` | `string \| null` | | — |

!!! warning "Workflow `agent_id` validation"
    On import, the `agent_id` is looked up in the database. If the agent does not
    exist the workflow is skipped and an error is recorded. Import agents first.

---

### `ExportedKnowledgeSource`

```json
{
  "name": "runbooks",
  "description": "Internal runbook vector store",
  "source_type": "vector_db",
  "connection_config": {
    "url": "http://qdrant:6333",
    "collection": "runbooks"
  },
  "tags": ["ops"]
}
```

| Field | Type | Required | Default |
|---|---|---|---|
| `name` | `string` | ✅ | — |
| `description` | `string` | | `""` |
| `source_type` | `string` | ✅ | `vector_db`, `mongo_db`, or `pgvector` |
| `connection_config` | `object` | | `{}` |
| `tags` | `string[]` | | `[]` |

---

## Response Schemas

### `ImportResult` (per-resource import response)

```json
{
  "created": 3,
  "errors": [],
  "ids": [
    "664f1a2b3c4d5e6f7a8b9c01",
    "664f1a2b3c4d5e6f7a8b9c02",
    "664f1a2b3c4d5e6f7a8b9c03"
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `created` | `integer` | Number of documents successfully created |
| `errors` | `string[]` | Per-item error messages for failed items |
| `ids` | `string[]` | MongoDB IDs of created documents |

### `BundleImportResult` (full bundle import response)

```json
{
  "skills":            { "created": 2, "errors": [], "ids": ["..."] },
  "agents":            { "created": 1, "errors": [], "ids": ["..."] },
  "workflows":         { "created": 1, "errors": [], "ids": ["..."] },
  "knowledge_sources": { "created": 1, "errors": [], "ids": ["..."] }
}
```

---

## Status Codes

| Code | Meaning |
|---|---|
| `200 OK` | Export succeeded |
| `201 Created` | Import succeeded (even if some items produced errors) |
| `401 Unauthorized` | Missing or invalid `Authorization` header |
| `404 Not Found` | Resource ID not found (single-resource export) |
| `422 Unprocessable Entity` | Request body failed schema validation |
