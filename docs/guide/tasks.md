# Tasks

Task executions are asynchronous workflow runs. The **Run Task** screen starts a new task, while **Task Executions** shows history and live status.

## Run a Task

1. Open **Run Task**.
2. Select a workflow.
3. Enter the prompt.
4. Optionally choose a reasoning effort override (`low`, `medium`, or `high`) when supported by the selected model path.
5. Submit the task.

The API creates a `TaskExecution` immediately and a Celery worker performs the run in the background.

## Monitor and Stop Tasks

The **Task Executions** page shows task status, workflow, agent, prompt, model, reasoning effort, timestamps, elapsed time, and tool-call counts. Use the workflow filter to narrow history.

Open task details to inspect:

- prompt and final response
- progress/todo state
- logs and streamed messages
- usage statistics
- worker and timing metadata

Running or pending tasks can be stopped from the UI or by calling `POST /api/tasks/{task_id}/stop`. The stop request signals the workflow halt event; the worker stops at the next safe checkpoint.

