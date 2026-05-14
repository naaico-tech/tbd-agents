# Tasks API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tasks` | List task executions for the current user |
| `GET` | `/api/tasks/{id}` | Get task execution |
| `GET` | `/api/tasks/{id}/progress` | Get current TODO/progress state |
| `GET` | `/api/tasks/workflow/{workflow_id}` | List executions for one workflow |
| `POST` | `/api/tasks/{id}/stop` | Request stop for a running or pending task |

---

## List Tasks

```
GET /api/tasks
```

Returns task execution history for workflows owned by the authenticated user. To filter by workflow, use `GET /api/tasks/workflow/{workflow_id}`.

**Response:** `200 OK` — Array of task execution objects.

---

## Get Task

```
GET /api/tasks/{id}
```

Returns a single task execution with status, timestamps, and error details (if any).

**Response:** `200 OK`

```json
{
  "id": "...",
  "workflow_id": "...",
  "status": "completed",
  "created_at": "2026-04-10T12:00:00Z",
  "completed_at": "2026-04-10T12:01:30Z",
  "error": null
}
```

---

## Task Progress

```
GET /api/tasks/{id}/progress
```

Returns the task's current todo/progress object:

```json
{
  "todos": [
    {"id": "inspect", "title": "Inspect repository", "status": "done"}
  ],
  "current_step": "running tests",
  "percent_complete": 75
}
```

---

## Workflow Tasks

```
GET /api/tasks/workflow/{workflow_id}
```

Returns summaries for executions belonging to one workflow.

---

## Stop Task

```
POST /api/tasks/{id}/stop
```

Signals the workflow halt event for a `running` or `pending` task.

**Response:** `202 Accepted`

```json
{
  "status": "halt_requested",
  "workflow_id": "..."
}
```
