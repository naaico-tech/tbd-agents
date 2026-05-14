# Workflows API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/workflows` | Create workflow |
| `GET` | `/api/workflows` | List workflows |
| `GET` | `/api/workflows/export` | Export all workflows |
| `GET` | `/api/workflows/{workflow_id}/export` | Export one workflow |
| `POST` | `/api/workflows/import` | Import workflow bundle |
| `GET` | `/api/workflows/{workflow_id}` | Get workflow |
| `PUT` | `/api/workflows/{workflow_id}` | Update workflow |
| `DELETE` | `/api/workflows/{workflow_id}` | Delete workflow |
| `POST` | `/api/workflows/{workflow_id}/prompt` | Start asynchronous task |
| `POST` | `/api/workflows/{workflow_id}/halt` | Halt running workflow |
| `GET` | `/api/workflows/{workflow_id}/stream` | SSE event stream |
| `POST` | `/api/workflows/{workflow_id}/skills/{skill_id}` | Attach skill |
| `DELETE` | `/api/workflows/{workflow_id}/skills/{skill_id}` | Detach skill |

## Fields

`title`, `agent_id`, `model`, `max_turns`, `skill_ids`, `skill_tags`, `output_format`, `infinite_session`, `caveman`, `bypass_memory`, `auto_memory`, `tsv_tool_results`, `reasoning_effort`, `guardrail_ids`, `guardrail_tags`, `repo_url`, `repo_branch`, `repo_token_name`, `credential_overrides`, `webhook_url`, and `error_webhook_url`.

Prompt body accepts either `prompt` or structured `request`, plus optional `reasoning_effort` override.

Resource-specific import/export is available at the endpoints above; see [Import & Export](import-export.md).
