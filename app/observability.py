"""Observability: OpenTelemetry tracing + Prometheus custom metrics.

Call ``init_telemetry()`` once at app startup to configure the OTEL
TracerProvider and auto-instrument FastAPI / HTTPX.

Custom Prometheus metrics are exposed as module-level singletons so that
``agent_engine.py`` can record token usage, cost, tool calls, etc.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# ── Custom Prometheus metrics ────────────────────────────────────────────────

tokens_total = Counter(
    "copilot_hub_tokens_total",
    "Total tokens consumed",
    ["direction", "model"],  # direction: input | output | cache_read | cache_write
)

cost_dollars_total = Counter(
    "copilot_hub_cost_dollars_total",
    "Total estimated cost in USD",
    ["model"],
)

premium_requests_total = Counter(
    "copilot_hub_premium_requests_total",
    "Total premium requests consumed",
    ["model"],
)

agent_tasks_total = Counter(
    "copilot_hub_agent_tasks_total",
    "Total agent tasks by status",
    ["status", "model", "reasoning_effort"],
)

agent_tasks_active = Gauge(
    "copilot_hub_agent_tasks_active",
    "Currently running agent tasks",
)

agent_task_duration_seconds = Histogram(
    "copilot_hub_agent_task_duration_seconds",
    "Duration of agent task execution",
    ["model", "status"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

tool_calls_total = Counter(
    "copilot_hub_tool_calls_total",
    "Total tool calls made",
    ["tool_name"],
)

tool_calls_per_task = Histogram(
    "copilot_hub_tool_calls_per_task",
    "Number of tool calls per task",
    ["model"],
    buckets=(1, 2, 5, 10, 20, 50, 100, 200),
)

cost_per_task_dollars = Histogram(
    "copilot_hub_cost_per_task_dollars",
    "Cost per task in USD",
    ["model"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 10),
)

mcp_connections_total = Counter(
    "copilot_hub_mcp_connections_total",
    "Total MCP server connections initiated",
    ["server_name"],
)

repo_sync_total = Counter(
    "copilot_hub_repo_sync_total",
    "Total repository sync operations",
    ["status"],  # success | failure
)

repo_sync_duration_seconds = Histogram(
    "copilot_hub_repo_sync_duration_seconds",
    "Duration of repository sync operations",
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)

sse_connections_active = Gauge(
    "copilot_hub_sse_connections_active",
    "Active SSE connections",
)


# ── Telemetry initialisation ────────────────────────────────────────────────


def init_telemetry(app=None):
    """Configure OTEL tracing and auto-instrument FastAPI + HTTPX.

    Args:
        app: The FastAPI application instance (for FastAPIInstrumentor).
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — telemetry disabled")
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", "copilot-agent-hub")
    resource_attrs = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")

    attrs = {"service.name": service_name}
    if resource_attrs:
        for pair in resource_attrs.split(","):
            k, _, v = pair.partition("=")
            if k and v:
                attrs[k.strip()] = v.strip()

    resource = Resource.create(attrs)
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument
    if app:
        FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    logger.info("OpenTelemetry initialised — exporting to %s", endpoint)
