# Skills API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/skills` | Create skill |
| `GET` | `/api/skills` | List skills |
| `GET` | `/api/skills/{id}` | Get skill |
| `PUT` | `/api/skills/{id}` | Update skill |
| `DELETE` | `/api/skills/{id}` | Delete skill |

---

## Create Skill

```
POST /api/skills
```

```json
{
  "name": "rca-format",
  "description": "Structures output as a Root Cause Analysis report",
  "instructions": "Structure your final output as an RCA report with sections: Summary, Timeline, Root Cause, Impact, Remediation, Prevention.",
  "tags": ["incident", "reporting"]
}
```

**Response:** `201 Created`

---

## List Skills

```
GET /api/skills
```

**Response:** `200 OK` — Array of skill objects.

---

## Get Skill

```
GET /api/skills/{id}
```

**Response:** `200 OK` — Single skill object.

---

## Update Skill

```
PUT /api/skills/{id}
```

**Response:** `200 OK`

---

## Delete Skill

```
DELETE /api/skills/{id}
```

**Response:** `204 No Content`


## Import/Export

Use `GET /api/skills/export`, `GET /api/skills/{skill_id}/export`, and `POST /api/skills/import`. See [Import & Export](import-export.md).
