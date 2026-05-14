---
icon: material/view-dashboard
---

# Architecture

TBD Agents is a distributed system designed to run custom AI agents at scale.

<div class="grid cards" markdown>

-   :material-sitemap:{ .lg .middle } **System Overview**

    ---

    Components, request flow, and how the pieces connect.

    [:octicons-arrow-right-24: System Overview](system-overview.md)

-   :material-database:{ .lg .middle } **Data Model**

    ---

    Entity relationships and document schemas.

    [:octicons-arrow-right-24: Data Model](data-model.md)

-   :material-arrow-expand-all:{ .lg .middle } **Scaling**

    ---

    Horizontal scaling strategies for workers, API, and infrastructure.

    [:octicons-arrow-right-24: Scaling](scaling.md)

</div>

---

## System at a Glance

```mermaid
graph LR
    Client([Client / Dashboard]) -->|HTTP| API[FastAPI API]
    API -->|Enqueue| Redis[(Redis)]
    Redis -->|Task| Worker[Celery Workers]
    Worker -->|SDK Session| SDK[Copilot SDK]
    SDK --> Models[Copilot Models API]
    SDK --> MCP[MCP Servers]
    Worker -->|Publish Events| Redis
    Redis -->|Subscribe| API
    API -->|SSE Stream| Client
    Worker -->|Persist| Mongo[(MongoDB)]
    API -->|Read/Write| Mongo
```

---

## Dashboard Integration Boundary

The Flutter dashboard is served from `/dashboard`, while the legacy static dashboard remains available at `/dashboard-legacy`. Its backend contract is already cleanly separated behind REST + streaming endpoints under `/api`.

- CRUD resources: agents, MCP servers, custom tools, skills, knowledge sources/items, guardrails, tokens, providers, workflows, memories, and scheduled agents
- Execution surfaces: `POST /api/workflows/{id}/prompt`, `POST /api/workflows/{id}/halt`, `GET /api/workflows/{id}/stream`, task history under `/api/tasks`
- Chat surfaces: `POST /api/agents/{id}/chat` plus persisted session endpoints under `/api/agents/{id}/chat/sessions`
- Dynamic form dependencies: model listing via `/api/models`, file uploads for knowledge items and custom tools, and workflow/task views that combine CRUD state with live streaming events

This makes the current UI a good candidate for a Flutter web replacement that preserves the feature set while keeping backend deployment and execution architecture unchanged.
