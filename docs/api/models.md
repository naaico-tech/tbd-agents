# Models API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/models` | List available models |

---

## List Models

```
GET /api/models
```

Returns the list of models available through the Copilot SDK.

**Response:** `200 OK`

```json
[
  {"id": "gpt-4.1", "name": "GPT-4.1"},
  {"id": "o3-mini", "name": "O3 Mini"},
  {"id": "claude-sonnet-4.5", "name": "Claude Sonnet 4.5"}
]
```

!!! note
    Available models depend on your GitHub Copilot subscription tier and the models enabled by your organization.
