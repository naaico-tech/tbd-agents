# Guardrails API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/guardrails` | Create guardrail |
| `GET` | `/api/guardrails` | List guardrails |
| `GET` | `/api/guardrails/{id}` | Get guardrail |
| `PUT` | `/api/guardrails/{id}` | Update guardrail |
| `DELETE` | `/api/guardrails/{id}` | Delete guardrail |

## Create Prompt Guardrail

```json
{
  "name": "no-secrets",
  "description": "Reject prompts containing obvious secrets",
  "guardrail_type": "prompt",
  "tags": ["security"],
  "enabled": true,
  "prompt_config": {
    "forbidden_patterns": ["AKIA[0-9A-Z]{16}"],
    "required_patterns": [],
    "max_length": 4000,
    "min_length": null
  }
}
```

Use `guardrail_type` and the matching config field:

- `prompt` → `prompt_config`
- `request` → `request_config` with `json_schema`
- `output` → `output_config` with pattern/length options, `pii_detection`, and `must_be_valid_json`

Do not use legacy `type` or `config` field names.
