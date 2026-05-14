# Scheduled Agents API

Scheduled Agents run a workflow prompt repeatedly on an interval.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/scheduled-agents` | Create schedule |
| `GET` | `/api/scheduled-agents` | List schedules |
| `GET` | `/api/scheduled-agents/{sa_id}` | Get schedule |
| `PATCH` | `/api/scheduled-agents/{sa_id}` | Update schedule fields |
| `PATCH` | `/api/scheduled-agents/{sa_id}/enable` | Enable schedule |
| `PATCH` | `/api/scheduled-agents/{sa_id}/disable` | Disable schedule |
| `DELETE` | `/api/scheduled-agents/{sa_id}` | Delete schedule |

## Create

```json
{
  "name": "Daily runbook review",
  "workflow_id": "<WORKFLOW_ID>",
  "prompt": "Review open production incidents and summarize risks.",
  "interval_value": 1,
  "interval_unit": "days",
  "start_at": "2026-05-01T09:00:00Z",
  "end_at": null
}
```

`interval_value` must be at least 1. `enabled`, `last_run_at`, and `next_run_at` are response fields.
