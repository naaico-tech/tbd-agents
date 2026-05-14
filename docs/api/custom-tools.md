# Custom Tools API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/custom-tools` | Create a custom tool |
| `GET` | `/api/custom-tools` | List all custom tools |
| `GET` | `/api/custom-tools/{id}` | Get a custom tool |
| `PUT` | `/api/custom-tools/{id}` | Update a custom tool |
| `DELETE` | `/api/custom-tools/{id}` | Delete a custom tool |
| `POST` | `/api/custom-tools/{id}/run` | Ad-hoc test run |
| `GET` | `/api/custom-tools/{id}/env-mapping` | Get token mapping for required environment variables |
| `PUT` | `/api/custom-tools/{id}/env-mapping` | Map required environment variables to stored token names |
| `POST` | `/api/custom-tools/validate` | Validate source (no save) |
| `POST` | `/api/custom-tools/upload` | Upload a `.py` file |

---

## Create Tool

```
POST /api/custom-tools
```

```json
{
  "name": "weather",
  "description": "Fetch current weather for a city",
  "source_code": "def weather(city: str, units: str = 'metric') -> dict:\n    return {\"city\": city}",
  "parameters_schema": null,
  "tags": ["utility"],
  "is_enabled": true
}
```

!!! note "Auto schema inference"
    If `parameters_schema` is omitted or `null`, the schema is inferred from the function's type annotations automatically.

**Response:** `201 Created`

```json
{
  "id": "6601a1b2c3d4e5f607890abc",
  "name": "weather",
  "description": "Fetch current weather for a city",
  "source_code": "...",
  "parameters_schema": {
    "type": "object",
    "properties": {
      "city":  {"type": "string"},
      "units": {"type": "string"}
    },
    "required": ["city"]
  },
  "tags": ["utility"],
  "is_enabled": true,
  "created_at": "2026-04-21T07:00:00Z",
  "updated_at": "2026-04-21T07:00:00Z"
}
```

---

## List Tools

```
GET /api/custom-tools
```

**Response:** `200 OK` — Array of tool objects.

---

## Get Tool

```
GET /api/custom-tools/{id}
```

**Response:** `200 OK` — Single tool object. `404 Not Found` if the ID does not exist.

---

## Update Tool

```
PUT /api/custom-tools/{id}
```

All fields are optional. Only provided fields are updated.

```json
{
  "description": "Updated description",
  "is_enabled": false
}
```

!!! note "Schema re-inference on source change"
    Updating `source_code` or `name` triggers automatic re-inference of `parameters_schema` unless you explicitly provide a new `parameters_schema` in the same request.

**Response:** `200 OK` — Updated tool object.  `422 Unprocessable Entity` if the new source fails validation.

---

## Delete Tool

```
DELETE /api/custom-tools/{id}
```

**Response:** `204 No Content`

---

## Ad-hoc Run

```
POST /api/custom-tools/{id}/run
```

```json
{
  "arguments": {
    "city": "London",
    "units": "metric"
  }
}
```

**Response:** `200 OK`

```json
{
  "tool_name": "weather",
  "result": "{\"city\": \"London\", \"temp\": 18}",
  "success": true,
  "error": null
}
```

| Status | Meaning |
|--------|---------|
| `200` | Execution completed (check `success` flag for tool-level errors) |
| `404` | Tool not found |
| `409 Conflict` | Tool is disabled |

---

## Environment Token Mapping

Bundled plugins and user-defined tools can declare `env_config` requirements. Use the mapping endpoints to bind those environment variables to encrypted token names without storing secrets in tool source.

```
GET /api/custom-tools/{id}/env-mapping
PUT /api/custom-tools/{id}/env-mapping
```

```json
{
  "env_mapping": {
    "DATADOG_API_KEY": "datadog-api-key",
    "DATADOG_APP_KEY": "datadog-app-key"
  }
}
```

Tool responses include `env_config` when a tool declares environment requirements and `is_plugin` when the tool is loaded from the plugin system.

---

## Validate Source

```
POST /api/custom-tools/validate
```

Validates source code and returns the inferred schema without persisting anything.

```json
{
  "name": "weather",
  "source_code": "def weather(city: str, units: str = 'metric') -> dict:\n    return {}"
}
```

**Response:** `200 OK`

```json
{
  "valid": true,
  "inferred_schema": {
    "type": "object",
    "properties": {
      "city":  {"type": "string"},
      "units": {"type": "string"}
    },
    "required": ["city"]
  },
  "error": null
}
```

On failure:

```json
{
  "valid": false,
  "inferred_schema": null,
  "error": "Function 'weather' not found in source"
}
```

---

## Upload `.py` File

```
POST /api/custom-tools/upload
```

Multipart form upload. The tool name is derived from the filename stem (e.g. `weather.py` → `weather`).

```bash
curl -X POST http://localhost:8000/api/custom-tools/upload \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -F "file=@weather.py"
```

**Response:** `201 Created` — Same shape as [Create Tool](#create-tool).

| Status | Meaning |
|--------|---------|
| `201` | Tool created |
| `400` | File does not have a `.py` extension |
| `422` | Source validation failed |

---

## Tool Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | MongoDB ObjectId |
| `name` | string | Function name (must match function in source) |
| `description` | string | Human-readable description (shown to the LLM) |
| `source_code` | string | Full Python source of the tool file |
| `parameters_schema` | object | JSON Schema for tool parameters |
| `tags` | string[] | Free-form categorisation tags |
| `is_enabled` | boolean | Whether the tool is active at runtime |
| `created_at` | datetime | Creation timestamp (UTC) |
| `updated_at` | datetime | Last update timestamp (UTC) |
