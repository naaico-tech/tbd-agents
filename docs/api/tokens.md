# Tokens API

Tokens are encrypted credentials used by providers, MCP/custom tools, repository checkout, and source connection settings.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tokens` | Store encrypted token |
| `GET` | `/api/tokens` | List token metadata |
| `GET` | `/api/tokens/{token_id}` | Get token metadata |
| `PUT` | `/api/tokens/{token_id}` | Update token value and/or description |
| `DELETE` | `/api/tokens/{token_id}` | Delete token |

## Create

```json
{
  "name": "datadog-api-key",
  "value": "secret-value",
  "description": "Datadog production API key"
}
```

Responses never include decrypted values. They include `description`, `masked_value`, and `created_by`:

```json
{
  "id": "...",
  "name": "datadog-api-key",
  "description": "Datadog production API key",
  "masked_value": "********1234",
  "created_by": "octocat",
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```
