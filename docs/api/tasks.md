# Tasks API

Task executions are created by workflow prompts and run asynchronously.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tasks` | List all task executions |
| `GET` | `/api/tasks/{task_id}` | Get task details including logs/messages/usage |
| `GET` | `/api/tasks/{task_id}/progress` | Get structured progress/todos |
| `GET` | `/api/tasks/workflow/{workflow_id}` | List task executions for one workflow |
| `POST` | `/api/tasks/{task_id}/stop` | Stop an active task |

`GET /api/tasks?workflow_id=...` is not supported; use `GET /api/tasks/workflow/{workflow_id}`.

## Task Object Highlights

Responses include `workflow_id`, `workflow_title`, `agent_name`, `prompt`, `status`, `model`, `reasoning_effort`, `tool_calls`, `response`, `progress`, `logs`, `messages`, `usage`, timestamps, and elapsed seconds.
