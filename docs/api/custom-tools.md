# Custom Tools API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/custom-tools` | Create custom tool from source |
| `GET` | `/api/custom-tools` | List tools, including plugins |
| `GET` | `/api/custom-tools/{tool_id}` | Get tool |
| `PUT` | `/api/custom-tools/{tool_id}` | Update tool |
| `GET` | `/api/custom-tools/{tool_id}/env-mapping` | Get env var/token mapping options |
| `PUT` | `/api/custom-tools/{tool_id}/env-mapping` | Update token mapping for env vars |
| `DELETE` | `/api/custom-tools/{tool_id}` | Delete user tool |
| `POST` | `/api/custom-tools/{tool_id}/run` | Ad-hoc run |
| `POST` | `/api/custom-tools/validate` | Validate source without saving |
| `POST` | `/api/custom-tools/upload` | Upload `.py` file |

## Create

```json
{
  "name": "weather",
  "description": "Fetch current weather for a city",
  "source_code": "def weather(city: str) -> dict:\n    return {\"city\": city}",
  "parameters_schema": {},
  "env_config": {"WEATHER_API_KEY": "{{token:weather-key}}"},
  "tags": ["utility"],
  "is_enabled": true
}
```

Responses include `env_config` and `is_plugin`. Plugin tools are loaded from the server plugin registry and are not created via upload.

## Env Mapping

```json
{
  "env_var_mapping": {
    "WEATHER_API_KEY": "weather-key"
  }
}
```

Mapping values are token names without the `{{token:...}}` wrapper. Empty string removes a token mapping while keeping the env var key.
