---
icon: material/view-dashboard
---

# Architecture

TBD Agents is a distributed, self-hosted agent platform built around FastAPI, Redis, Celery workers, model/provider SDKs, MCP/custom tools, and a pluggable data layer.

<div class="grid cards" markdown>

-   :material-sitemap:{ .lg .middle } **System Overview**

    [:octicons-arrow-right-24: System Overview](system-overview.md)

-   :material-database:{ .lg .middle } **Data Model**

    [:octicons-arrow-right-24: Data Model](data-model.md)

-   :material-arrow-expand-all:{ .lg .middle } **Scaling**

    [:octicons-arrow-right-24: Scaling](scaling.md)

</div>

## Dashboard Integration Boundary

The Flutter dashboard is served from `/dashboard`. The legacy static dashboard is served from `/dashboard-legacy`; `/dashboard-new-ui` remains a compatibility alias. UI functionality is behind REST and streaming endpoints under `/api`.

- CRUD resources: agents, MCP servers, custom tools, skills, knowledge sources/items, guardrails, tokens, providers, workflows, memories, and scheduled agents.
- Execution: `POST /api/workflows/{id}/prompt`, workflow halt/stream endpoints, and task history under `/api/tasks`.
- Chat: `POST /api/agents/{id}/chat` plus API-only persisted session endpoints.
- Data: MongoDB + Qdrant (`qdrant` profile) or PostgreSQL + pgvector (`pgvector` profile).
