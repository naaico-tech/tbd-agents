---
hide:
  - navigation
  - toc
---

# TBD Agents

<p style="font-size: 1.3em; opacity: 0.85;">
<strong>Your agents. Your rules. Your infrastructure.</strong>
</p>

---

TBD Agent lets you build, control, and trigger your own custom AI agents over the web — no black boxes, no vendor lock-in, just a clean API backed by the GitHub Copilot SDK that you run on your own infrastructure.

Spin up purpose-built agents with distinct system prompts, wire them to any MCP tool server, send a prompt over HTTP, and watch them work in real-time through streaming Server-Sent Events. Need to scale? Celery workers distribute agent execution across as many nodes as you want.

!!! tip "TBD — *To Be Decided* by you"
    What your agents do, which tools they use, and how far they go.

---

## Highlights

- :house: **Fully self-hosted** — runs on your infra via Docker Compose; no SaaS dependency beyond GitHub Copilot billing
- :robot: **Custom agents over HTTP** — create, configure, and trigger agents with a simple REST API or the built-in dashboard
- :zap: **Real-time streaming** — SSE endpoint streams logs, messages, token-by-token responses, and usage metrics live
- :twisted_rightwards_arrows: **Distributed workers** — Celery + Redis architecture lets you scale agent execution horizontally
- :wrench: **MCP tool ecosystem** — connect any MCP-compatible tool server (Datadog, Jira, Notion, Slack, and more)
- :infinity: **Infinite sessions** — automatic context compaction keeps long-running agents alive
- :chart_with_upwards_trend: **Usage & cost tracking** — per-workflow token counts, premium request quotas, and cost data
- :jigsaw: **Skills system** — modular instruction sets installed per workflow to shape agent behaviour
- :books: **Knowledge bases** — vector databases (Qdrant) or file/text uploads with automatic retrieval

---

## Quick Start

```bash
git clone https://github.com/naaico-tech/tbd-agents.git && cd tbd-agents

# Create your environment file and fill in at least GITHUB_TOKEN
cp .env.example .env

docker-compose up --build
```

| Endpoint | URL |
|---|---|
| Dashboard | [http://localhost:8000/dashboard](http://localhost:8000/dashboard) |
| API Docs (Swagger) | [http://localhost:8000/docs](http://localhost:8000/docs) |
| API Base | [http://localhost:8000/api](http://localhost:8000/api) |

---

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Agent engine | GitHub Copilot SDK (JSON-RPC) |
| Task queue | Celery + Redis |
| Event bus | Redis Pub/Sub |
| Database | MongoDB + Beanie ODM |
| Vector DB | Qdrant (optional, for knowledge) |
| Frontend | Single-page dashboard (JS, SSE) |
| Containers | Docker Compose |

---

<p style="text-align: center; opacity: 0.6;">
Built by <a href="https://www.naaico.com"><strong>NAAICO</strong></a> — Navigate · Automate · Accelerate · Innovate · Create · Optimise
</p>
