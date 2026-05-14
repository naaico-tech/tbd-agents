---
icon: material/database-export
---

# Import & Export

Import and export let you back up your TBD Agents configuration, migrate between environments (dev → staging → production), and share setups with teammates.

---

## Use Cases

- **Backup & restore** — Snapshot all skills, agents, workflows, and knowledge sources before a major change.
- **Environment promotion** — Export from a local or staging instance, import into production.
- **Team sharing** — Share a curated agent + skill bundle as a JSON file.
- **Disaster recovery** — Keep a periodic export in version control or object storage.

---

## Export

### Full System Export

Exports every skill, agent, your own workflows, and all knowledge sources in a single JSON bundle.

```bash
curl -X GET http://localhost:8000/api/export \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -o my-backup.json
```

### Export All Resources of One Type

=== "Skills"

    ```bash
    curl -X GET http://localhost:8000/api/skills/export \
      -H "Authorization: Bearer $GITHUB_TOKEN"
    ```

=== "Agents"

    ```bash
    curl -X GET http://localhost:8000/api/agents/export \
      -H "Authorization: Bearer $GITHUB_TOKEN"
    ```

=== "Workflows"

    ```bash
    curl -X GET http://localhost:8000/api/workflows/export \
      -H "Authorization: Bearer $GITHUB_TOKEN"
    ```

=== "Knowledge Sources"

    ```bash
    curl -X GET http://localhost:8000/api/knowledge-sources/export \
      -H "Authorization: Bearer $GITHUB_TOKEN"
    ```

### Export a Single Resource

```bash
# Export one skill
curl -X GET http://localhost:8000/api/skills/<SKILL_ID>/export \
  -H "Authorization: Bearer $GITHUB_TOKEN"

# Export one agent
curl -X GET http://localhost:8000/api/agents/<AGENT_ID>/export \
  -H "Authorization: Bearer $GITHUB_TOKEN"

# Export one workflow
curl -X GET http://localhost:8000/api/workflows/<WORKFLOW_ID>/export \
  -H "Authorization: Bearer $GITHUB_TOKEN"

# Export one knowledge source
curl -X GET http://localhost:8000/api/knowledge-sources/<KS_ID>/export \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```

---

## Export Bundle Format

### Full Bundle (`GET /api/export`)

```json
{
  "version": "1.0",
  "exported_at": "2026-04-28T10:00:00+00:00",
  "resource_type": "bundle",
  "skills": [
    {
      "name": "rca-format",
      "description": "Structures output as a Root Cause Analysis report",
      "instructions": "Structure your final output as an RCA report with sections: Summary, Timeline, Root Cause, Impact, Remediation, Prevention.",
      "tags": ["incident", "reporting"]
    }
  ],
  "agents": [
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
  ],
  "workflows": [
    {
      "title": "Incident Response",
      "agent_id": "664f1a2b3c4d5e6f7a8b9c0d",
      "model": "gpt-4o",
      "max_turns": 10,
      "skill_ids": [],
      "skill_tags": ["incident"],
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
  ],
  "knowledge_sources": [
    {
      "name": "runbooks",
      "description": "Internal runbook vector store",
      "source_type": "mongodb_vector",
      "connection_config": {
        "collection": "runbooks",
        "index_name": "vector_index"
      },
      "tags": ["ops"]
    }
  ]
}
```

### Per-Resource Bundle (`GET /api/skills/export`)

```json
{
  "version": "1.0",
  "exported_at": "2026-04-28T10:00:00+00:00",
  "resource_type": "skill",
  "items": [
    {
      "name": "rca-format",
      "description": "Structures output as a Root Cause Analysis report",
      "instructions": "Structure output as an RCA report.",
      "tags": ["incident"]
    }
  ]
}
```

---

## Import

### Full System Import

```bash
curl -X POST http://localhost:8000/api/import \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d @my-backup.json
```

### Import Resources of One Type

=== "Skills"

    ```bash
    curl -X POST http://localhost:8000/api/skills/import \
      -H "Authorization: Bearer $GITHUB_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "items": [
          {
            "name": "rca-format",
            "description": "RCA report formatter",
            "instructions": "Structure output as an RCA report.",
            "tags": ["incident"]
          }
        ]
      }'
    ```

=== "Agents"

    ```bash
    curl -X POST http://localhost:8000/api/agents/import \
      -H "Authorization: Bearer $GITHUB_TOKEN" \
      -H "Content-Type: application/json" \
      -d @agents-bundle.json
    ```

=== "Workflows"

    ```bash
    curl -X POST http://localhost:8000/api/workflows/import \
      -H "Authorization: Bearer $GITHUB_TOKEN" \
      -H "Content-Type: application/json" \
      -d @workflows-bundle.json
    ```

=== "Knowledge Sources"

    ```bash
    curl -X POST http://localhost:8000/api/knowledge-sources/import \
      -H "Authorization: Bearer $GITHUB_TOKEN" \
      -H "Content-Type: application/json" \
      -d @knowledge-bundle.json
    ```

---

## Import Responses

### Success

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

### Partial Failure

Individual item errors are captured without aborting the rest of the batch:

```json
{
  "created": 2,
  "errors": [
    "bad-workflow: agent_id \"664f000000000000deadbeef\" not found"
  ],
  "ids": [
    "664f1a2b3c4d5e6f7a8b9c01",
    "664f1a2b3c4d5e6f7a8b9c02"
  ]
}
```

### Full Bundle Import Response

The full bundle import (`POST /api/import`) returns a result per resource type:

```json
{
  "skills": { "created": 2, "errors": [], "ids": ["..."] },
  "agents": { "created": 1, "errors": [], "ids": ["..."] },
  "workflows": { "created": 1, "errors": ["bad-workflow: agent_id not found"], "ids": [] },
  "knowledge_sources": { "created": 1, "errors": [], "ids": ["..."] }
}
```

---

## Import Behaviour

!!! note "Always creates new documents"
    Import never deduplicates or updates existing resources. Each item in the bundle
    is always inserted as a new document, even if a resource with the same name
    already exists.

!!! note "Partial failure handling"
    If one item in a batch fails (e.g. a validation error or database constraint),
    that item's error is appended to `errors[]` and the rest of the batch continues.
    The import is never aborted mid-batch.

!!! warning "Workflow `agent_id` validation"
    When importing workflows (via either the per-resource or full bundle endpoint),
    each workflow's `agent_id` is validated against the database **before** creation.
    If the referenced agent does not exist, the workflow is skipped and an error is
    recorded. Import agents **before** importing workflows to avoid this.

!!! note "Workflow ownership"
    Imported workflows are assigned to the authenticated GitHub user regardless of
    who owned them in the source system.

---

## Flutter UI

!!! tip "EXPORT / IMPORT buttons in the UI"
    Every resource list screen (Skills, Agents, Workflows, Knowledge Sources) has
    **EXPORT** and **IMPORT** buttons in the top-right corner. These call the same
    endpoints and handle the file picker/download automatically — no curl required.
