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

```json
{
  "name": "openai",
  "config": {
    "api_key": "...",
    "base_url": "https://api.openai.com/v1"
  }
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
