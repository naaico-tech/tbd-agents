# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2025-07-15

First public release of **TBD Agents** — a multi-agent API hub powered by the GitHub Copilot SDK, Anthropic Claude, and the Model Context Protocol (MCP).

### Added

#### Core Agent Runtimes
- **GitHub Copilot SDK** integration as the primary agent runtime with full tool-calling support.
- **Anthropic Claude Agent SDK** (M1) integration — Claude models available as a first-class agent runtime alongside Copilot.
- **Google ADK** runtime support for agents running on Google's Agent Development Kit.

#### MCP & Tool System
- **Model Context Protocol (MCP)** tool support — agents can connect to any MCP-compatible server (stdio and SSE transports).
- Per-agent MCP server configuration stored in MongoDB; connections managed at runtime.
- Built-in MCP credential management for Datadog, Atlassian/Jira, and custom servers.

#### Skills System
- **Skills** — modular, reusable instruction sets that can be attached to agents and workflows.
- Skill tags for fine-grained workflow routing.
- Prompt context budgeting and clipping: skills are trimmed to fit within the model's context window.
- Static prefix length tracking and system-prompt caching for efficiency.

#### Workflows & Task Queue
- **Workflows** — multi-step agent execution pipelines with configurable skill sets and tool selections.
- **Celery** task queue (backed by Redis + RedBeat) for async and scheduled workflow execution.
- TSV tool-result formatting for structured workflow context.
- Infinite-session workflow support (24-hour session timeout).

#### Scheduled Agents
- **Scheduled agent** functionality: define cron-like schedules persisted in MongoDB and executed by the Celery Beat scheduler.
- Race-condition-free scheduled trigger execution.

#### Knowledge Base Management
- **Knowledge sources** with MongoDB document storage and **Qdrant** vector search.
- Semantic retrieval via `fastembed` embeddings stored in Qdrant.
- GridFS bucket support for large knowledge item payloads.
- Per-knowledge-source connection testing endpoint (`/api/knowledge-sources/<id>/test`).

#### Agent Memory System
- **Agent memory** (M2): persistent per-agent memory stored in MongoDB with optional Qdrant-backed semantic search.
- Memory event logging with classification and styled log output.
- Semantic memory retrieval via Qdrant for context-aware recall.
- Prompt context budgeting integrates memories alongside skills within the token budget.

#### Guardrails
- Input and **output guardrails** with configurable rules per agent.
- `output_config` field on Guardrail documents for fine-grained output filtering.

#### BYOK (Bring Your Own Key) Provider Support
- **BYOK providers** (M3): register OpenAI, Anthropic, Azure OpenAI, or any OpenAI-compatible endpoint.
- Per-request and server-level token injection; per-request tokens always take priority.
- Encrypted token storage using `cryptography` (Fernet); `TOKEN_ENCRYPTION_KEY` environment variable.
- Providers collection in MongoDB; full CRUD API.
- Full Copilot SDK feature parity for BYOK providers (tool-calling, streaming, model selection).

#### Real-Time SSE Streaming
- **Server-Sent Events (SSE)** streaming for agent responses — clients receive tokens as they are generated.
- Event bus assigns monotonic event IDs; clients can send `Last-Event-ID` to replay missed events.
- Redis-backed SSE pub/sub for multi-worker deployments.
- Halt signal support: clients can cancel an in-progress agent run.
- Passive agent chat with self-awareness context injection (M7).

#### Observability
- **Prometheus** metrics exposed on `/metrics` (API) and a dedicated worker metrics port.
- **OpenTelemetry** instrumentation for FastAPI, HTTPX, and Celery with OTLP gRPC exporter.
- **Grafana** dashboards, **Tempo** distributed tracing, **Loki** log aggregation, and **Promtail** log shipping — all pre-configured in Docker Compose.
- Alert rules in `observability/alert-rules.yml`.
- Context-engineering observability metrics: token budget usage, semantic retrieval hit rates.
- Celery queue length and active SSE connection metrics (fixed race condition in counter wiring).

#### Import / Export API
- **Import/Export** REST endpoints for Skills, Agents, Workflows, and Knowledge Sources — enables full platform portability.
- Bulk export returns a single archive; bulk import validates and upserts all resources atomically.

#### Plugin System
- **PluginBase** framework: drop-in Python plugins with automatic discovery.
- **YAML plugin registry** (`plugins/registry.yaml`) — register plugins without code changes.

#### Flutter Web UI
- Full-featured **retro-themed Flutter web UI** (Retro Dawn colour scheme) with native-screen parity for all API surfaces:
  - Dashboard, Agents, Workflows, Skills, Knowledge Base, Memory, MCP Servers, Providers, Scheduled Agents, Import/Export, and Settings pages.
- Responsive layout; served as static assets from the FastAPI app.
- Tool checkbox state synchronisation and improved UX polish.

#### Deployment
- **Docker Compose** stack: API server, Celery worker, Celery Beat scheduler, MongoDB, Redis, Qdrant, and the full observability stack (OTel Collector, Prometheus, Tempo, Loki, Promtail, Grafana).
- **Multi-stage optimised Docker image** with layer caching — significantly reduced image size and build times.
- **Helm chart** (`helm/tbd-agents`) for Kubernetes deployments.
- OpenTelemetry resource attributes (`service.version`, `deployment.environment`) injected via environment variables in all three service containers.

#### Developer Experience
- `uv` for dependency management and virtual-environment isolation.
- **Ruff** linter and formatter (target: Python 3.12, line length 100).
- **Pytest** test suite with `pytest-asyncio` (auto mode); unit and integration test layers.
- `docker-compose.test.yml` for isolated integration test runs.
- MkDocs Material documentation site with architecture diagrams, API reference, and migration guide.

### Dependencies (key)

| Package | Version |
|---|---|
| `fastapi` | ≥ 0.115.0 |
| `beanie` | ≥ 1.26.0, < 2.0.0 |
| `celery[redis]` | ≥ 5.4.0 |
| `celery-redbeat` | ≥ 2.2.0 |
| `qdrant-client` | ≥ 1.9.0 |
| `anthropic` | ≥ 0.42.0 |
| `mcp` | ≥ 1.8.0 |
| `opentelemetry-api` | ≥ 1.29.0 |
| `prometheus-fastapi-instrumentator` | ≥ 7.0.0 |
| `cryptography` | ≥ 43.0.0 |

---

[Unreleased]: https://github.com/naaico-tech/tbd-agents/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/naaico-tech/tbd-agents/releases/tag/v0.1.0
