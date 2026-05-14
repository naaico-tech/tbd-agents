# Workflows

A workflow ties an agent to an execution template. Tasks, schedules, and prompts run through workflows.

## Workflow Fields

| Field | Description |
|---|---|
| Title | Optional display name |
| Agent | Required agent ID |
| Model override | Optional model for this workflow |
| Max turns | Maximum tool-call rounds |
| Skills / skill tags | Explicit skill IDs and tag-based skill selection |
| Guardrails / guardrail tags | Explicit guardrail IDs and tag-based guardrail selection |
| Output format | `json` or `markdown` |
| Reasoning effort | `low`, `medium`, or `high`; can be overridden when running a task |
| Status | `active` or `inactive` |
| Infinite session | Enables long-running context compaction |
| Bypass memory | Skips memory injection for task runs |
| Auto memory | Extracts memories after task completion |
| TSV tool results | Formats tool results for compact tabular consumption |
| Caveman | Produces terser final responses and compresses injected context |
| Credential overrides | Map plugin/custom-tool env vars to token names for this workflow |
| Repo URL / branch / token | Optional repository checkout settings for repo-aware tasks |
| Webhook URL | Called after task completion |
| Error webhook URL | Called after task failure |

## Create a Workflow

```bash
curl -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Incident Response",
    "agent_id": "<AGENT_ID>",
    "max_turns": 10,
    "output_format": "markdown",
    "reasoning_effort": "medium",
    "skill_tags": ["incident"],
    "guardrail_tags": ["safe-output"],
    "infinite_session": true
  }'
```

## Run a Prompt

```bash
curl -X POST http://localhost:8000/api/workflows/<WORKFLOW_ID>/prompt \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Investigate the latest production alerts.", "reasoning_effort": "high"}'
```

The API returns quickly with a `task_id`; execution continues on a Celery worker. Follow live progress with the workflow stream or review it later in [Task Executions](tasks.md).

## Halt a Running Workflow

```bash
curl -X POST http://localhost:8000/api/workflows/<WORKFLOW_ID>/halt \
  -H "Authorization: Bearer $GITHUB_TOKEN"
```
