# Observability & Monitoring

TBD Agents ships a full **MELT** (Metrics, Events, Logs, Traces) stack
powered by OpenTelemetry, Prometheus, Grafana, Loki, and Tempo.

```
┌───────────────┐  ┌───────────────┐
│  FastAPI app   │  │ Celery worker │
│  :8000/metrics │  │  :9101/metrics│
└───────┬───────┘  └───────┬───────┘
        │ OTLP gRPC        │ OTLP gRPC
        ▼                  ▼
   ┌─────────────────────────┐
   │   OTel Collector :4317  │
   │   Prometheus :8889      │
   └──────┬──────────┬───────┘
          │          │
          ▼          ▼
   ┌───────────┐  ┌──────┐  ┌──────┐
   │Prometheus │  │Tempo │  │ Loki │
   │  :9090    │  │:3200 │  │:3100 │
   └─────┬─────┘  └──┬───┘  └──┬───┘
         │           │         │
         ▼           ▼         ▼
       ┌──────────────────────────┐
       │     Grafana :3000        │
       │  admin / copilot         │
       └──────────────────────────┘
```

---

## Quick Start

All observability services start automatically with Docker Compose:

```bash
docker compose up -d
```

Open Grafana at [http://localhost:3000](http://localhost:3000) — default
credentials: `admin` / `copilot`.

---

## Custom Prometheus Metrics

The app defines **14 custom metrics** in `app/observability.py`.  All are
recorded by the agent engine during task execution and exposed via
`/metrics` (app) and `:9101/metrics` (worker).

### Counters

| Metric | Labels | Description |
|--------|--------|-------------|
| `copilot_hub_tokens_total` | `direction`, `model` | Total tokens consumed (input, output, cache_read, cache_write) |
| `copilot_hub_cost_dollars_total` | `model` | Estimated LLM cost in USD |
| `copilot_hub_premium_requests_total` | `model` | Premium API requests consumed |
| `copilot_hub_agent_tasks_total` | `status`, `model`, `reasoning_effort` | Agent tasks by outcome |
| `copilot_hub_tool_calls_total` | `tool_name` | Tool invocations by name |
| `copilot_hub_mcp_connections_total` | `server_name` | MCP server connections initiated |
| `copilot_hub_repo_sync_total` | `status` | Repository sync operations (success/failure) |

### Histograms

| Metric | Labels | Buckets | Description |
|--------|--------|---------|-------------|
| `copilot_hub_agent_task_duration_seconds` | `model`, `status` | 1s – 30min | Task execution time |
| `copilot_hub_tool_calls_per_task` | `model` | 1 – 200 | Tool calls per task |
| `copilot_hub_cost_per_task_dollars` | `model` | $0.001 – $10 | Cost distribution per task |
| `copilot_hub_repo_sync_duration_seconds` | — | 0.5s – 60s | Repo sync duration |

### Gauges

| Metric | Description |
|--------|-------------|
| `copilot_hub_agent_tasks_active` | Currently running agent tasks |
| `copilot_hub_sse_connections_active` | Active SSE connections |
| `copilot_hub_celery_queue_length` | Tasks waiting in the Celery queue |

---

## Scrape Targets

Prometheus is configured with three scrape jobs
(`observability/prometheus.yml`):

| Job | Target | Metrics |
|-----|--------|---------|
| `fastapi` | `app:8000/metrics` | FastAPI instrumentator + custom app metrics |
| `celery-worker` | `worker:9101/metrics` | All custom metrics recorded in worker processes |
| `otel-collector` | `otel-collector:8889` | OTel Collector internal metrics |

---

## Grafana Dashboards

Two pre-provisioned dashboards are available in Grafana.

### Overview (`copilot-hub-overview`)

Six rows covering the full system:

- **API Overview** — Request rate, latency percentiles, error rate
- **Agent Executions** — Active tasks, completion rate, duration percentiles
- **Token & Cost** — Input/output tokens, cost accumulation, premium requests
- **Tool Calls** — Call rate by tool, top tools (24h bar chart)
- **MCP Servers** — Connection rate, repo sync operations + p95 duration
- **System Resources** — Celery queue depth, active SSE connections, in-flight HTTP

### LLM & Cost Analytics (`copilot-hub-llm`)

Deep dive into model usage and spend:

- **Summary stats** — Total tokens, cost, premium requests, success rate (24h)
- **Token usage** — Input vs output over time, cache hit rates
- **Cost analysis** — Cost over time, cost-per-task distribution
- **Model performance** — Duration by model, tasks by status/reasoning effort
- **Traces** — Recent distributed traces via Tempo
- **Logs** — Combined app + worker logs via Loki

Both dashboards include **template variables** (`model`, `job`) for
filtering panels interactively.

---

## Alerting Rules

Prometheus evaluates alerting rules from `observability/alert-rules.yml`.
All rules are pre-configured — no Alertmanager is required for rule
evaluation, but you should add one to receive notifications.

| Alert | Condition | Severity | Description |
|-------|-----------|----------|-------------|
| `HighTaskFailureRate` | >25% failure rate for 5m | critical | Agent tasks are failing at high rate |
| `NoTaskCompletions` | Tasks submitted but none complete for 15m | warning | Workers may be stuck |
| `CostSpikeHourly` | >$50 in 1 hour | warning | Unexpected LLM spend |
| `CostSpikeDaily` | >$500 in 24 hours | critical | Major cost incident |
| `CeleryQueueBacklog` | >10 tasks queued for 5m | warning | Processing falling behind |
| `CeleryQueueCritical` | >50 tasks queued for 2m | critical | Workers overwhelmed or down |
| `WorkerDown` | Metrics endpoint unreachable for 2m | critical | Celery worker unreachable |
| `AppDown` | Metrics endpoint unreachable for 2m | critical | FastAPI app unreachable |
| `SlowTaskExecution` | p95 duration >5 min for 10m | warning | Tasks taking unusually long |
| `HighSSEConnections` | >100 active SSE for 5m | warning | Possible connection leak |

### Adding Alertmanager

To receive alert notifications, add Alertmanager to your
`docker-compose.yml`:

```yaml
alertmanager:
  image: prom/alertmanager:v0.27.0
  volumes:
    - ./observability/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
  ports:
    - "9093:9093"
```

Then add to `prometheus.yml`:

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]
```

---

## Distributed Tracing

OpenTelemetry auto-instruments FastAPI, HTTPX, and Celery. Traces flow
through the OTel Collector to Tempo.

- **App service name:** `tbd-agents-api`
- **Worker service name:** `tbd-agents-worker`

View traces in Grafana → Explore → Tempo, or use the embedded trace panel
in the LLM Analytics dashboard.

### Correlating Logs and Traces

Promtail extracts `trace_id` from log lines. In Grafana's Loki explorer,
click a trace ID to jump directly to the corresponding trace in Tempo.

---

## Troubleshooting

### No metrics in Prometheus

1. Check the targets page: [http://localhost:9090/targets](http://localhost:9090/targets)
2. Ensure `app:8000/metrics` and `worker:9101/metrics` show as **UP**
3. If the worker target is DOWN, verify `WORKER_METRICS_PORT=9101` is set

### Dashboards show "No data"

- Metrics only appear after at least one agent task has been executed
- Check the time range in Grafana (default is last 6h for Overview, 24h
  for LLM Analytics)
- Run a test workflow to generate initial data

### High Celery queue length

- Check worker logs: `docker compose logs worker --tail=100`
- Scale workers: `docker compose up -d --scale worker=3`
- When scaling, each worker instance needs a unique external port

### Traces not appearing in Tempo

- Verify `OTEL_EXPORTER_OTLP_ENDPOINT` is set in both app and worker
- Check OTel Collector logs: `docker compose logs otel-collector --tail=50`
- Ensure Tempo is receiving data: [http://localhost:3200/ready](http://localhost:3200/ready)
