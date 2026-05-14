# Scheduled Agents API

Scheduled agents run a saved workflow prompt on a recurring interval. They are owned through the referenced workflow: users can only manage schedules for workflows they own.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/scheduled-agents` | Create and register a schedule |
| `GET` | `/api/scheduled-agents` | List schedules for the current user |
| `GET` | `/api/scheduled-agents/{sa_id}` | Get one schedule |
| `PATCH` | `/api/scheduled-agents/{sa_id}` | Update name, prompt, interval, or dates |
| `PATCH` | `/api/scheduled-agents/{sa_id}/enable` | Enable a disabled schedule |
| `PATCH` | `/api/scheduled-agents/{sa_id}/disable` | Disable an active schedule without deleting it |
| `DELETE` | `/api/scheduled-agents/{sa_id}` | Delete the schedule and remove its Beat entry |

---

## Create Scheduled Agent

```
POST /api/scheduled-agents
```

```json
{
  "name": "daily-doc-review",
  "workflow_id": "<WORKFLOW_ID>",
  "prompt": "Review the documentation backlog and summarize priority updates.",
  "interval_value": 1,
  "interval_unit": "days",
  "start_at": "2026-05-15T09:00:00Z",
  "end_at": null
}
```

`interval_value` must be at least `1`. `interval_unit` is the schedule unit supported by the backend scheduler, such as `minutes`, `hours`, or `days`.

**Response:** `201 Created`

```json
{
  "id": "...",
  "name": "daily-doc-review",
  "workflow_id": "<WORKFLOW_ID>",
  "prompt": "Review the documentation backlog and summarize priority updates.",
  "interval_value": 1,
  "interval_unit": "days",
  "start_at": "2026-05-15T09:00:00Z",
  "end_at": null,
  "enabled": true,
  "last_run_at": null,
  "next_run_at": "2026-05-15T09:00:00Z",
  "created_at": "...",
  "updated_at": "..."
}
```

---

## Update or Toggle a Schedule

Use `PATCH /api/scheduled-agents/{sa_id}` to change schedule fields. Changing `interval_value`, `interval_unit`, `start_at`, or `end_at` rebuilds the RedBeat entry so the new cadence takes effect.

```json
{
  "prompt": "Run the weekly release readiness checklist.",
  "interval_value": 1,
  "interval_unit": "weeks"
}
```

Use `/enable` and `/disable` to toggle execution while keeping the schedule record.

