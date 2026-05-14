# Run Task and Task Executions

Tasks are asynchronous executions created by prompting a workflow.

## Run Task Dashboard Page

1. Select a workflow.
2. Enter a prompt.
3. Optionally override reasoning effort with `low`, `medium`, or `high`.
4. Click **Run**.
5. Watch status, output, turn counts, and live logs.
6. Click **Stop** to halt the active workflow run.

The page calls `POST /api/workflows/{workflow_id}/prompt`, polls task details, and falls back to `GET /api/tasks/workflow/{workflow_id}` if the prompt response does not include a `task_id`.

## Task Executions Dashboard Page

The Task Executions page shows execution history with auto-refresh and workflow filtering. The details dialog includes:

- original prompt and final response
- status, model, reasoning effort, tool-call count, elapsed time, and turn count/progress
- usage information
- conversation messages
- execution logs
- stop controls for active tasks

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/tasks` | List all task executions |
| `GET` | `/api/tasks/{task_id}` | Full task details |
| `GET` | `/api/tasks/{task_id}/progress` | Structured todo/progress information |
| `GET` | `/api/tasks/workflow/{workflow_id}` | Task history for one workflow |
| `POST` | `/api/tasks/{task_id}/stop` | Stop an active task |
| `POST` | `/api/workflows/{workflow_id}/halt` | Halt the workflow run |
