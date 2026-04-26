# Models API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/models` | List available models |

---

## List Models

```
GET /api/models
```

Returns the list of models available through the selected provider surface.

- Default / no `provider_id`: lists models from the Copilot SDK.
- `provider_id=<github_copilot-provider>`: lists models for that stored Copilot token.
- `provider_id=<google_adk-provider>`: lists chat-capable Google models exposed by the
  Google GenAI SDK for that provider's Gemini API key or Vertex AI config.

**Response:** `200 OK`

```json
[
  {"id": "gpt-4.1", "name": "GPT-4.1"},
  {"id": "o3-mini", "name": "O3 Mini"},
  {"id": "claude-sonnet-4.5", "name": "Claude Sonnet 4.5"}
]
```

**Google ADK response shape**

When `provider_id` references a `google_adk` provider, the response is narrowed to
models that support `generateContent` and uses this shape:

```json
[
  {
    "id": "gemini-2.5-flash",
    "name": "Gemini 2.5 Flash",
    "provider_type": "google_adk",
    "description": "Fast Gemini model",
    "input_token_limit": 1048576,
    "output_token_limit": 8192,
    "supported_actions": ["generateContent"]
  }
]
```

!!! note
    Available models depend on your GitHub Copilot subscription tier and the models enabled by your organization.

!!! note
    `google_adk` model listing never falls back to the request `Authorization` header.
    Gemini API providers require a stored provider token. Vertex AI providers can run
    keyless when `google_use_vertex_ai` is enabled and both
    `google_cloud_project` and `google_cloud_location` are set.
