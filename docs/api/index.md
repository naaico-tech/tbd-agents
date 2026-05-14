---
icon: material/api
---

# API Reference

Complete REST API reference for TBD Agents.

All endpoints except `/health` require an `Authorization: Bearer <token>` header. A server-level `GITHUB_TOKEN` can be configured, but clients may also supply per-request/provider tokens where supported.

!!! tip "Interactive API docs"
    The Swagger UI at [http://localhost:8000/docs](http://localhost:8000/docs) provides a fully interactive API explorer with request/response schemas.

---

## Resources

<div class="grid cards" markdown>

-   **[Agents](agents.md)** — Create and manage AI agents
-   **[Skills](skills.md)** — Reusable instruction modules
-   **[MCP Servers](mcp-servers.md)** — Tool server registration and testing
-   **[Workflows](workflows.md)** — Execution contexts, prompts, and streaming
-   **[Knowledge](knowledge.md)** — Knowledge sources and items
-   **[Providers](providers.md)** — Provider configuration
-   **[Tokens](tokens.md)** — Encrypted token storage
-   **[Guardrails](guardrails.md)** — Safety policy enforcement
-   **[Scheduled Agents](scheduled-agents.md)** — Recurring workflow prompts
-   **[Tasks](tasks.md)** — Task execution history
-   **[Models](models.md)** — Available model listing
-   **[Import & Export](import-export.md)** — JSON bundle backup and restore

</div>

---

## Authentication

Most API requests are authenticated with a Bearer token. Agent execution through GitHub/Copilot needs a token with the `copilot` scope; BYOK/provider flows may use stored provider tokens:

```bash
curl -H "Authorization: Bearer ghp_your_token_here" \
  http://localhost:8000/api/agents
```

---

## Health Check

```
GET /health
```

Returns the health status of the API. No authentication required.

