# Workflows API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/workflows` | Create workflow |
| `GET` | `/api/workflows` | List your workflows |
| `GET` | `/api/workflows/{id}` | Get workflow state + logs + messages |
| `PUT` | `/api/workflows/{id}` | Update workflow |
| `DELETE` | `/api/workflows/{id}` | Delete workflow |
| `POST` | `/api/workflows/{id}/prompt` | Send prompt (async execution) |
| `POST` | `/api/workflows/{id}/halt` | Halt running workflow |
| `GET` | `/api/workflows/{id}/stream` | SSE stream of real-time events |
| `POST` | `/api/workflows/{id}/skills/{skill_id}` | Install skill |
| `DELETE` | `/api/workflows/{id}/skills/{skill_id}` | Remove skill |
| `GET` | `/api/workflows/export` | Export all workflows |
| `GET` | `/api/workflows/{id}/export` | Export one workflow |
| `POST` | `/api/workflows/import` | Import workflows |

---

## Create Workflow

```
POST /api/workflows
```

```json
{
  "agent_id": "<AGENT_ID>",
  "model": "gpt-4.1",
  "max_turns": 10,
  "output_format": "markdown",
  "reasoning_effort": "medium",
  "skill_tags": ["incident"],
  "guardrail_tags": ["safe-output"],
  "infinite_session": true,
  "bypass_memory": false,
  "auto_memory": true,
  "tsv_tool_results": false,
  "caveman": true
}
```

Current workflow schemas also support `title`, `skill_ids`, `guardrail_ids`, credential overrides, repository fields (`repo_url`, `repo_branch`, `repo_token_name`), `webhook_url`, and `error_webhook_url`.

**Response:** `201 Created`

---

## Send Prompt

```
POST /api/workflows/{id}/prompt
```

```json
{
  "prompt": "Investigate the latest production alerts."
}
```

Returns `201` immediately. The agent runs asynchronously on a Celery worker. Connect to the SSE stream to follow progress.

---

## SSE Stream

```
GET /api/workflows/{id}/stream
```

Server-Sent Events endpoint. Streams real-time events:

| Event | Payload | Description |
|---|---|---|
| `log` | `{event, detail}` | Agent lifecycle events |
| `message` | `{role, content}` | Complete assistant/tool message |
| `message_delta` | `{delta}` | Streaming token fragment |
| `usage` | `{total_in, total_out, cost...}` | Cumulative usage stats |
| `status` | `{status, current_turn}` | Workflow state changes |

---

## Halt Workflow

```
POST /api/workflows/{id}/halt
```

Stops a running workflow.

**Response:** `200 OK`

---

## Install / Remove Skill

```
POST   /api/workflows/{id}/skills/{skill_id}   # Install
DELETE /api/workflows/{id}/skills/{skill_id}   # Remove
```

---

## List Workflows

```
GET /api/workflows
```

**Response:** `200 OK` — Array of workflow objects.

---

## Get Workflow

```
GET /api/workflows/{id}
```

Returns the full workflow state including messages, logs, and usage.

**Response:** `200 OK`

---

## Update Workflow

```
PUT /api/workflows/{id}
```

**Response:** `200 OK`

---

## Delete Workflow

```
DELETE /api/workflows/{id}
```

**Response:** `204 No Content`
