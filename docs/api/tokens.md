# Tokens API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tokens` | Store encrypted token |
| `GET` | `/api/tokens` | List tokens (values hidden) |
| `GET` | `/api/tokens/{id}` | Get token metadata |
| `PUT` | `/api/tokens/{id}` | Update token value or description |
| `DELETE` | `/api/tokens/{id}` | Delete token |

---

## Store Token

```
POST /api/tokens
```

```json
{
  "name": "datadog-api-key",
  "value": "your-secret-value",
  "description": "Datadog API key"
}
```

The value is encrypted at rest using the `TOKEN_ENCRYPTION_KEY`.

**Response:** `201 Created`

!!! warning
    Token values are write-only. The `GET` endpoints return metadata but never the decrypted value.

---

## List Tokens

```
GET /api/tokens
```

Returns token metadata (`id`, `name`, `description`, `masked_value`, `created_by`, timestamps). Values are always masked and never decrypted in API responses.

**Response:** `200 OK`

---

## Get Token

```
GET /api/tokens/{id}
```

Returns one token metadata object with `masked_value`.

---

## Update Token

```
PUT /api/tokens/{id}
```

```json
{
  "value": "rotated-secret-value",
  "description": "Rotated Datadog API key"
}
```

All fields are optional. If `value` is provided, it is encrypted before storage.

---

## Delete Token

```
DELETE /api/tokens/{id}
```

**Response:** `204 No Content`
