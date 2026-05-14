# Custom Tools

Custom Tools expose Python functions to agents. They include both user-created tools and bundled plugins loaded from `app/plugins.yaml`.

## Dashboard Behavior

The current Flutter Custom Tools page is primarily a management and inspection surface:

- lists bundled plugin tools and user-created tools
- shows enabled/disabled state, tags, schemas, and counts
- shows `is_plugin` for bundled plugins
- displays `env_config` requirements and maps required environment variables to stored Tokens
- can test or update supported metadata depending on the tool type

Creating a new user tool from pasted source, uploading a `.py` file, editing source code, or deleting tools is API-first. Plugins are loaded at startup from the configured plugin registry and are not authored in the dashboard.

## API Fields

| Field | Description |
|---|---|
| `name` | Function/tool name |
| `description` | Description shown to the model |
| `source_code` | Python source for user tools |
| `parameters_schema` | JSON Schema; inferred from type hints when omitted |
| `env_config` | Environment requirements; values can reference `{{token:name}}` |
| `tags` | Free-form labels |
| `is_enabled` | Whether the tool is active |
| `is_plugin` | Response-only flag for bundled plugin tools |

## Credential Mapping

Use the env mapping endpoints to assign stored tokens to a tool's required environment variables:

```bash
curl http://localhost:8000/api/custom-tools/<TOOL_ID>/env-mapping \
  -H "Authorization: Bearer $GITHUB_TOKEN"

curl -X PUT http://localhost:8000/api/custom-tools/<TOOL_ID>/env-mapping \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"env_var_mapping": {"SLACK_BOT_TOKEN": "slack-prod"}}'
```

## Runtime Notes

- User tools run in a fresh Python subprocess with a 30-second timeout.
- Disabled tools return `409 Conflict` on ad-hoc run and are skipped during execution.
- Copilot SDK workflows should use MCP servers for tool use; BYOK and Claude paths can invoke custom tools directly.
