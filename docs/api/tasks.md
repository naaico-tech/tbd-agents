# Tasks API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tasks` | List task executions (optional `?workflow_id=`) |
| `GET` | `/api/tasks/{id}` | Get task execution |

---

## List Tasks

```
GET /api/tasks
GET /api/tasks?workflow_id=<WF_ID>
```

Returns task execution history. Optionally filter by workflow.

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
