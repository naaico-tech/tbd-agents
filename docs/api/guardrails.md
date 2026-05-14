# Guardrails API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/guardrails` | Create guardrail |
| `GET` | `/api/guardrails` | List guardrails |
| `GET` | `/api/guardrails/{id}` | Get guardrail |
| `PUT` | `/api/guardrails/{id}` | Update guardrail |
| `DELETE` | `/api/guardrails/{id}` | Delete guardrail |

---

## Create Guardrail

```
POST /api/guardrails
```

```json
{
  "name": "no-pii",
  "description": "Blocks prompts containing PII",
  "guardrail_type": "prompt",
  "tags": ["safety"],
  "enabled": true,
  "prompt_config": {
    "forbidden_patterns": ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
    "required_patterns": [],
    "max_length": 4000
  }
}
```

Use `prompt_config` for `guardrail_type: "prompt"`, `request_config` with a `json_schema` for `request`, and `output_config` for output policies such as PII detection or valid-JSON enforcement.

**Response:** `201 Created`

---

## List Guardrails

```
GET /api/guardrails
```

**Response:** `200 OK` — Array of guardrail objects.

---

## Get Guardrail

```
GET /api/guardrails/{id}
```

**Response:** `200 OK`

---

## Update Guardrail

```
PUT /api/guardrails/{id}
```

**Response:** `200 OK`

---

## Delete Guardrail

```
DELETE /api/guardrails/{id}
```

**Response:** `204 No Content`
