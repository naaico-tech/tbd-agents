# Guardrails

Guardrails enforce policy around prompts, structured requests, and model outputs.

## Types and Fields

| Type | Required config | Common fields |
|---|---|---|
| `prompt` | `prompt_config` | `forbidden_patterns`, `required_patterns`, `max_length`, `min_length` |
| `request` | `request_config` | `json_schema` |
| `output` | `output_config` | `forbidden_patterns`, `required_patterns`, `max_length`, `pii_detection`, `must_be_valid_json` |

All guardrails also have `name`, `description`, `tags`, and an `enabled` toggle. Workflows can select guardrails explicitly or by tag.

## Prompt Guardrail Example

```bash
curl -X POST http://localhost:8000/api/guardrails \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "no-secrets",
    "description": "Reject prompts containing obvious secrets",
    "guardrail_type": "prompt",
    "tags": ["security"],
    "enabled": true,
    "prompt_config": {
      "forbidden_patterns": ["AKIA[0-9A-Z]{16}"],
      "max_length": 4000
    }
  }'
```

## Request and Output Guardrails

- Request guardrails validate a structured `request` object sent to the workflow prompt endpoint with JSON Schema.
- Output guardrails validate final responses. They can block forbidden patterns, require patterns, enforce max length, detect likely PII, and require valid JSON.

Disabled guardrails remain stored but are ignored during execution.
