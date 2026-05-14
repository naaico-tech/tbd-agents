# Tokens API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tokens` | Store encrypted token |
| `GET` | `/api/tokens` | List tokens (values hidden) |
| `DELETE` | `/api/tokens/{id}` | Delete token |

---

## Store Token

```
POST /api/tokens
```

```json
{
  "name": "datadog-api-key",
  "value": "your-secret-value"
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

Returns token metadata (name, id, created date). Values are always hidden.

**Response:** `200 OK`

---

## Delete Token

```
DELETE /api/tokens/{id}
```

**Response:** `204 No Content`
