# Providers API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/providers` | Register provider |
| `GET` | `/api/providers` | List providers |
| `GET` | `/api/providers/{id}` | Get provider |
| `PUT` | `/api/providers/{id}` | Update provider |
| `DELETE` | `/api/providers/{id}` | Delete provider |

---

## Register Provider

```
POST /api/providers
```

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Unique provider name |
| `provider_type` | string | Yes | One of: `github_copilot`, `openai`, `anthropic`, `azure_openai`, `custom` |
| `api_key_token_name` | string | Yes | Name of the encrypted token storing the API key |
| `base_url` | string | No | Override base URL (required for `azure_openai` and `custom`) |
| `azure_api_version` | string | No | Azure OpenAI API version (default: `2024-12-01-preview`) |
| `azure_deployment` | string | No | Azure deployment name (defaults to workflow model) |
| `description` | string | No | Human-readable description |

=== "Anthropic (Claude Agent SDK)"

    ```json
    {
      "name": "claude-provider",
      "provider_type": "anthropic",
      "api_key_token_name": "anthropic-key",
      "description": "Claude Agent SDK provider"
    }
    ```

    Uses the Claude Agent SDK (`beta.agents/sessions`) for a full server-side agentic runtime with native MCP support, custom tools, and streaming events. No `base_url` needed.

=== "OpenAI"

    ```json
    {
      "name": "openai-provider",
      "provider_type": "openai",
      "api_key_token_name": "openai-key"
    }
    ```

=== "Azure OpenAI"

    ```json
    {
      "name": "azure-provider",
      "provider_type": "azure_openai",
      "api_key_token_name": "azure-key",
      "base_url": "https://myresource.openai.azure.com",
      "azure_deployment": "gpt-4o",
      "azure_api_version": "2024-12-01-preview"
    }
    ```

=== "GitHub Copilot"

    ```json
    {
      "name": "copilot-byok",
      "provider_type": "github_copilot",
      "api_key_token_name": "github-pat"
    }
    ```

**Response:** `201 Created`

---

## List Providers

```
GET /api/providers
```

**Response:** `200 OK` — Array of provider objects.

---

## Get Provider

```
GET /api/providers/{id}
```

**Response:** `200 OK`

---

## Update Provider

```
PUT /api/providers/{id}
```

**Response:** `200 OK`

---

## Delete Provider

```
DELETE /api/providers/{id}
```

**Response:** `204 No Content`
