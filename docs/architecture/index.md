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
