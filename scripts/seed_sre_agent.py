#!/usr/bin/env python3
"""Provision SRE skills, an Anthropic provider, and the hero-mechanic agent.

Usage
-----
    # From repo root:
    python scripts/seed_sre_agent.py
        --anthropic-key sk-ant-...    (optional — skip to create agent without provider)
        --base-url http://localhost:8000
        --github-token <pat>          (or set GITHUB_TOKEN env var)

The script is idempotent: resources whose names already exist are skipped.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

# ---------------------------------------------------------------------------
# SRE Skills
# ---------------------------------------------------------------------------

_SKILLS: list[dict] = [
    {
        "name": "sre-jira-triage",
        "description": (
            "Playbook for triaging a Jira issue during SRE debugging sessions. "
            "Covers how to fetch and extract structured facts from a Jira ticket "
            "(symptom, affected integration, environment, time of onset, resolution "
            "status). Enforces read-only access — NEVER create, modify, or transition tickets."
        ),
        "tags": ["sre", "jira", "triage"],
        "instructions": """\
# SRE Jira Triage Skill

Use this skill when you need to extract structured debugging context from a Jira issue.

---

## Constraints

- **Read-only.** You MUST NOT create, edit, transition, comment on, or otherwise modify any Jira issue.
- **Lookback window.** Jira queries: 30-day maximum.

---

## Input

A Jira ticket number (e.g., `MIMS-55317`). If the ticket number is not available, ask the user before proceeding.

---

## Extraction Checklist

Fetch the issue using the Jira MCP tool. Extract every field below. If a field is absent, record `Unknown`.

| Field | What to capture |
|-------|----------------|
| **Reported symptom** | Exact customer description of the problem |
| **Affected integration** | Zid / Salla / Bonat / other TSP |
| **Environment** | production / staging / unknown |
| **Time of onset** | Exact timestamp (ISO 8601) or closest approximate window |
| **Reporter** | Name / team — for context only, no contact |
| **Assignee** | Name / team — for context only, no contact |
| **Resolution status** | Open / In Progress / Resolved / Closed |
| **Linked issues** | Any blocked-by, relates-to, or duplicate links |
| **Key comments** | Any comment that clarifies root cause, workarounds, or timelines |

---

## Output Format

Emit the triage block in this structure, to be embedded under **Section 2.1** of the final RCA report:

```markdown
### 2.1 Jira Triage

- **Ticket**: [ISSUE-NUMBER](https://rewaatech.atlassian.net/browse/[ISSUE-NUMBER])
- **Reported Symptom**: ...
- **Affected Integration**: ...
- **Environment**: ...
- **Time of Onset**: ...
- **Reporter**: ...
- **Assignee**: ...
- **Resolution Status**: ...
- **Linked Issues**: ...
- **Key Comments**: ...
```

Pass `Time of Onset` downstream to the Datadog log/trace query step as the anchor timestamp.
""",
    },
    {
        "name": "sre-datadog-logs-traces",
        "description": (
            "Playbook for pulling error logs and distributed traces from Datadog during "
            "SRE debugging sessions. Covers filter strategy, 7-day lookback rule, "
            "integration-scoped queries, and output table format. "
            "Read-only — never create or modify Datadog resources."
        ),
        "tags": ["sre", "datadog", "logs", "traces"],
        "instructions": """\
# SRE Datadog Logs & Traces Skill

Use this skill after Jira triage when you need corroborating evidence from Datadog logs and traces.

---

## Constraints

- **Read-only.** MUST NOT create or modify any Datadog monitor, dashboard, notebook, or log pipeline.
- **Lookback window.** Maximum **7 days** anchored to the time of onset supplied by the Jira triage step. If onset is unknown, use the full 7-day window and search for the first occurrence of the symptom pattern.

---

## Query Strategy

Apply filters in this order to reduce noise:

1. **Service** — `REWAA-REPO/src/main/integrations/` (integrations backend)
2. **Level** — `ERROR` and `WARN` only
3. **Integration identifier** — one of: `salla`, `zid`, `bonat`, `tsp`, or the merchant ID if known from the Jira triage
4. **Time window** — 7 days back from onset timestamp

Run **log search** first, then pull **traces** for any trace IDs surfaced in the log results.

---

## Output Format

For each significant log entry, add a row to this table:

| Timestamp | Service | Level | Message | Trace ID |
|-----------|---------|-------|---------|----------|
| ISO 8601 | service-name | ERROR/WARN | truncated message | trace-id or — |

If no relevant logs are found in the window, record `No relevant log entries found in 7-day window`.

For traces, note:
- Trace ID
- Root span service and operation
- Total duration
- First error span (service, operation, error message)

Emit findings under **Section 2.2** of the final RCA report.

---

## Escalation Trigger

If the error volume is **> 100 occurrences/hour** sustained for > 30 minutes, flag this as a potential **P1 incident pattern** and note it prominently.
""",
    },
    {
        "name": "sre-datadog-metrics",
        "description": (
            "Playbook for querying and correlating Datadog metrics during SRE debugging "
            "sessions. Covers which metrics to pull (error rate, latency, queue depth), "
            "how to identify anomalies, and how to record findings for RCA correlation. "
            "Read-only — never create or modify Datadog resources."
        ),
        "tags": ["sre", "datadog", "metrics"],
        "instructions": """\
# SRE Datadog Metrics Skill

Use this skill after pulling logs/traces to check whether metric anomalies corroborate the symptom window.

---

## Constraints

- **Read-only.** MUST NOT create or modify any Datadog monitor, dashboard, notebook, or metric configuration.
- **Lookback window.** Maximum **7 days** anchored to the onset timestamp from Jira triage.

---

## Metrics to Pull

Query all three categories below for the affected integration service:

### 1. Error Rate

- Metric: request error rate for the integrations backend
- Filter by service and integration identifier (zid / salla / bonat)
- Look for step-changes or spikes at or just before the onset timestamp

### 2. Latency

- Metrics: `p50`, `p95`, `p99` for relevant endpoints
- Endpoints of interest: sync endpoints, webhook handlers, order/product fetch endpoints
- Note any sustained elevation or sudden spike

### 3. Queue Depth

- Metrics: sync job queue depth, webhook ingestion queue depth
- Look for backlog growth (queue depth rising without draining) or sudden drops (unexpected flush/purge)

---

## Anomaly Recording Format

For each anomaly found, record:

```
- Metric: <metric name>
- Window: <start ISO 8601> → <end ISO 8601>
- Observed value: <value or trend description>
- Baseline (prior 24h avg): <value>
- Correlation with onset: <yes / approximate / no>
```

If no anomalies are found: record `No metric anomalies detected in 7-day window`.

Emit findings under **Section 2.3** of the final RCA report.
""",
    },
    {
        "name": "sre-api-contract-check",
        "description": (
            "Playbook for verifying the current API contract of third-party integrations "
            "(Zid, Salla, Bonat) during SRE debugging. Covers endpoint existence, request/"
            "response schema changes, auth flow changes, and pagination/rate-limit changes. "
            "Uses Zid and Salla Docs MCP tools. Read-only — never modify source files."
        ),
        "tags": ["sre", "api", "contract", "zid", "salla", "bonat"],
        "instructions": """\
# SRE API Contract Check Skill

Use this skill when Datadog evidence implicates a Zid, Salla, or Bonat integration failure, to determine whether a third-party API contract change is the root cause.

---

## Constraints

- **Read-only.** MUST NOT modify any source file in the `rewaatech-mims` repository.
- Only applicable when the affected integration is **Zid**, **Salla**, or **Bonat**.

---

## Tools

| Integration | MCP Tool |
|-------------|----------|
| Zid | `zid-open-apis` MCP |
| Salla | `salla-docs` MCP (apidog, site-id 451700) |
| Bonat | Use available docs MCP or web fetch |

---

## Verification Checklist

For the affected integration, check all four areas:

### 1. Endpoint Existence

- Identify the endpoints the backend calls (read from `$REWAA_BASE_PATH/src/main/integrations/` — do NOT modify)
- Confirm each endpoint still exists at the documented URL in the current API spec
- Flag any endpoints that have been deprecated, moved, or removed

### 2. Request / Response Schema

- Compare field names, data types, and required fields between the backend's expected schema and the current API spec
- Flag any fields that have been renamed, changed type, or made required/optional

### 3. Authentication Flow

- Check the current auth scheme (OAuth2, API key, token refresh flow)
- Compare against what the backend implements
- Flag any scheme changes (e.g., token lifetime changes, new required headers, endpoint changes for token exchange)

### 4. Pagination & Rate Limits

- Check current pagination strategy (cursor vs offset, max page size)
- Check documented rate limits (requests/min, burst limits)
- Flag any changes that could cause partial data sync or 429 errors

---

## Output Format

Emit findings under **Section 2.4** of the final RCA report:

```markdown
### 2.4 API Contract Check

**Integration**: Zid / Salla / Bonat

#### Endpoint Existence
- ✅ /endpoint — present
- ❌ /old-endpoint — removed (was used by backend at src/...)

#### Request / Response Schema
- ⚠️ Field `product_id` renamed to `sku_id` in response body

#### Authentication Flow
- ✅ No changes detected

#### Pagination & Rate Limits
- ⚠️ Max page size reduced from 100 → 50 items
```

If no contract differences are found: record `No API contract changes detected`.
""",
    },
    {
        "name": "sre-integrations-navigator",
        "description": (
            "Playbook for navigating the rewaatech-mims integrations codebase during SRE "
            "debugging. Covers the primary source folders, event-driven ECS architecture, "
            "inbound/outbound flow per TSP (Zid, Salla, Bonat, Grubtech), and how to locate "
            "the right handler for any given failure. Read-only — never modify source files."
        ),
        "tags": ["sre", "integrations", "code", "navigation"],
        "instructions": """\
# SRE Integrations Navigator Skill

Use this skill when you need to locate code relevant to an integration failure — to understand which handler was invoked, which event topic carried the message, and where the failure point sits in the flow.

---

## Constraints

- **Read-only.** MUST NOT create, edit, or delete any source file.
- **Two primary folders only.** All integration logic lives in exactly two places:
  - `src/main/integrations/` — NestJS backend service
  - `src/main/angular/` — Angular frontend (merchant-facing UI)
- **No Lambda / serverless.** The service runs entirely on **ECS** (Elastic Container Service). There are no Lambda functions in the integration flow.
- **Event broker is SQS/SNS.** Use `@ListenForEvent(Topics.X)` decorators to find consumers.

---

## Architecture Overview

```
TSP Webhook (Salla/Zid/Grubtech HTTP POST)
        │
        ▼
src/main/integrations/src/modules/web-hooks/{salla,local,grubtech}/
        │  (validates payload, emits SQS topic)
        ▼
AWS SQS Queue  (FIFO or Standard — see TopicMapObj in topics.ts)
        │
        ▼
@ListenForEvent(Topics.X) — NestJS listener on ECS task
        │
        ▼
Command / Service handler (commands/ or services/ inside each module)
        │
        ▼
Outbox pattern (src/libs/event/outbox/) — for downstream events
```

---

## Primary Folder Map

### `src/main/integrations/src/`

| Folder | Purpose |
|--------|---------|
| `modules/orders/` | Inbound order creation/update from Zid, Salla, Grubtech; outbound order status |
| `modules/products/` | Product sync (create/update/delete/quantity) from TSP channels |
| `modules/batches/` | Batch product export/publish orchestration |
| `modules/sync-external-products/` | Pull-based sync of external TSP product catalogue |
| `modules/bonat/` | Bonat loyalty — invoice-generated events, push-order flow |
| `modules/web-hooks/salla/` | Salla inbound webhook handler |
| `modules/web-hooks/grubtech/` | Grubtech inbound webhook handler |
| `libs/event/` | Event broker wiring — `Topics` enum, `TopicMapObj`, `@ListenForEvent`, outbox |
| `libs/external-api-services/` | HTTP clients to Zid, Salla, Bonat external APIs |
| `libs/observability/` | Datadog tracing, `@ObservedService` decorator |

---

## Key Order Topics

| Topic | Queue | Consumer |
|-------|-------|----------|
| `Topics.ZidOrders` | FIFO | `OrderListenerService.zidOrderListener` |
| `Topics.SallaOrders` | FIFO | `OrderListenerService.sallaOrderListener` |
| `Topics.GrubtechOrders` | FIFO | `OrderListenerService.grubtechOrderListener` |
| `Topics.InvoiceGenerated` | Queue | Bonat `invoiceGeneratedListener` |
| `Topics.PushOrderToBonatV2` | Queue | Bonat `pushOrderToBonatListener` |

## Key Product Topics

| Topic | Queue | Consumer |
|-------|-------|----------|
| `Topics.ZidProducts` | FIFO | product sync listener |
| `Topics.SallaProductsV2` | FIFO | product sync listener |
| `Topics.UpdateMultipleProduct` | FIFO | product batch update |
| `Topics.StockUpdateNotification` | Fanout FIFO | stock level broadcast |

---

## How to Find a Handler for a Failing Event

1. Identify the topic name from logs/Jira (pattern: `integration-*`, `zid-*`, `salla-*`, `bonat-*`)
2. Look up the enum in `src/libs/event/topics.ts`
3. Search for `@ListenForEvent(Topics.X)` across `src/modules/`
4. Trace listener → command/service handler (1–3 hops)
5. Check outbox (`src/libs/event/outbox/`) if a downstream event never published

**DLQ pattern:** Every FIFO queue has `deadLetterQueueEnabled: true`. DLQ names appear in Datadog as `<topic-name>-dlq`.

---

## TSP-Specific Entry Points

### Zid
- Orders: `Topics.ZidOrders` → `OrderListenerService.zidOrderListener`
- Products: `Topics.ZidProducts` → product listener
- Token refresh: `Topics.RefreshZidTokens`

### Salla
- Orders: `Topics.SallaOrders` → `OrderListenerService.sallaOrderListener`
- Products: `Topics.SallaProductsV2` → product listener
- Webhook: `src/modules/web-hooks/salla/` (HMAC validation → SQS topic)

### Bonat
- Invoice: `Topics.InvoiceGenerated` → `BonatService.handleInvoiceGenerated`
- Push order: `Topics.PushOrderToBonatV2` → `BonatService.handlePushOrder`
- Files: `src/modules/bonat/bonat.listener.ts`, `bonat.service.ts`

### Grubtech
- Orders: `Topics.GrubtechOrders` → `OrderListenerService.grubtechOrderListener`
- Webhook: `src/modules/web-hooks/grubtech/`

---

## Common Failure Patterns

| Symptom | Where to look |
|---------|--------------|
| Order not created | `modules/orders/commands/create-order/`, DLQ for `ZidOrders`/`SallaOrders` |
| Product not syncing | `modules/products/commands/create-update-product/` |
| Batch export stalled | `modules/batches/services/`, `commands/check-batch-sync/` |
| Bonat push failing | `modules/bonat/bonat.service.ts`, `Topics.PushOrderToBonatV2` DLQ |
| Webhook not processed | `modules/web-hooks/{salla,grubtech}/` — HMAC validation, payload parsing |
| Event never consumed | `src/libs/event/outbox/outbox.service.ts` |

---

## Output

Emit findings under **Section 2.5** of the RCA report (Code Navigation sub-section):

- **Topic identified**: `Topics.X`
- **Consumer method**: class + method
- **File path**: relative from `src/main/integrations/`
- **Call chain**: listener → service → command
- **DLQ name** (if applicable)
""",
    },
    {
        "name": "sre-rca-synthesis",
        "description": (
            "Playbook for synthesizing findings from Jira triage, Datadog logs/traces, "
            "Datadog metrics, and API contract checks into a structured Root Cause Analysis. "
            "Covers the cross-source correlation matrix, evidence labelling rules "
            "(Confirmed / PRELIMINARY / HYPOTHESIS), and how to draft fix recommendations."
        ),
        "tags": ["sre", "rca", "synthesis"],
        "instructions": """\
# SRE RCA Synthesis Skill

Use this skill after all evidence has been gathered (Jira, Datadog logs/traces, Datadog metrics, API contract check) to produce a structured RCA and proposed fix.

---

## Cross-Source Correlation Matrix

| Symptom | Primary Source | Corroborating Source |
|---------|---------------|----------------------|
| API errors (4xx/5xx) | Datadog logs | Jira reported symptom |
| Sync failures (Zid/Salla) | Datadog traces | Zid/Salla API contract check |
| Performance degradation | Datadog metrics | Datadog traces / Jira |
| User-reported bugs | Jira | Datadog logs at reported time |
| Auth failures | Datadog logs | API contract check (auth flow) |
| Partial/missing data | Datadog logs | API contract check (schema/pagination) |

---

## Evidence Labelling Rules

| Label | Rule |
|-------|------|
| **Confirmed** | Supported by evidence from ≥ 2 independent sources |
| **[PRELIMINARY]** | Supported by exactly 1 source |
| **[HYPOTHESIS]** | Inferred from patterns; no direct artifact — MUST include a `Verification step:` line |

Never omit the label. Never upgrade a single-source finding to Confirmed.

---

## RCA Structure (Section 3)

```markdown
## 3. Root Cause Analysis

### Confirmed Findings
- **Finding**: <description>
  **Evidence**: <source 1> + <source 2>

### [PRELIMINARY] Findings
- **[PRELIMINARY] Finding**: <description>
  **Evidence**: <single source>

### [HYPOTHESIS] Inferences
- **[HYPOTHESIS]**: <description>
  **Verification step**: <how to confirm or refute>
```

---

## Proposed Fix Guidelines (Section 4)

- Provide **code-level** suggestions: file path, function name, description — do NOT apply the change
- Prefix each item: `[Code]`, `[Config]`, or `[Process]`
- Every item must trace back to a finding in Section 3

```markdown
## 4. Proposed Fix

> ⚠️ Recommendations only. No changes have been applied by the debugger.

- [Code] `src/.../products.service.ts` — update `fetchProducts()` to use new `sku_id` field
- [Config] Reduce batch size from 100 to 50 to match new Salla page size limit
- [Process] Add API contract smoke test to CI pipeline for Salla endpoints
```
""",
    },
    {
        "name": "sre-write-rca-report",
        "description": (
            "Playbook for writing the final structured RCA Markdown report to disk and "
            "publishing it to Confluence. Covers file path convention, mandatory section "
            "order, section content rules, and the Confluence target folder. Always produces "
            "a report even when the RCA is inconclusive."
        ),
        "tags": ["sre", "rca", "report", "confluence"],
        "instructions": """\
# SRE Write RCA Report Skill

Use this skill as the final step after RCA synthesis to materialise the report file and publish to Confluence.

---

## Output File

Create the file at:

```
~/ai-docs/debugging/[ISSUE-NUMBER].md
```

Create parent directories if they do not exist. Overwrite if the file already exists.

---

## Mandatory Report Template

```markdown
# RCA Report: [ISSUE-NUMBER]

**Date**: YYYY-MM-DD
**Jira**: [ISSUE-NUMBER](https://rewaatech.atlassian.net/browse/[ISSUE-NUMBER])
**Affected Integration**: [Zid / Salla / Bonat / other]
**Affected Service/Component**: [service path]
**Report Status**: [Confirmed RCA / Preliminary / Inconclusive]

---

## 1. Issue Summary

[One paragraph: problem statement, who reported it, environment, time of onset.]

---

## 2. Evidence Collected

### 2.1 Jira Triage
[Output from sre-jira-triage skill]

### 2.2 Datadog Logs & Traces
[Output from sre-datadog-logs-traces skill]

### 2.3 Datadog Metrics
[Output from sre-datadog-metrics skill]

### 2.4 API Contract Check
[Output from sre-api-contract-check skill, or "Not applicable"]

---

## 3. Root Cause Analysis

[Output from sre-rca-synthesis skill — Confirmed / PRELIMINARY / HYPOTHESIS findings]

---

## 4. Proposed Fix

> ⚠️ Recommendations only. No changes have been applied by the debugger.

[Output from sre-rca-synthesis skill — [Code] / [Config] / [Process] items]

---

## 5. Follow-Up Actions

[Next steps for engineers]
```

---

## Report Status Rules

| Status | When to use |
|--------|------------|
| **Confirmed RCA** | Root cause has ≥ 2 corroborating sources |
| **Preliminary** | Root cause has exactly 1 source |
| **Inconclusive** | Insufficient evidence; include what was ruled out and next steps |

---

## Confluence Publishing (Optional)

After writing the file, create or overwrite a Confluence page:

- **Space**: MIMS
- **Parent folder**: Heroes → TSP subfolder (`https://rewaatech.atlassian.net/wiki/spaces/MIMS/folder/4112056325`)
- **Page title**: The Jira issue number (e.g., `MIMS-55317`)

Use the Confluence MCP tool. Skip if the MCP is unavailable.

Confirm the report file path to the user once written.
""",
    },
]

# ---------------------------------------------------------------------------
# SRE Agent system prompt
# ---------------------------------------------------------------------------

_AGENT_NAME = "hero-mechanic"

_SYSTEM_PROMPT = """\
You are **hero-mechanic**, a read-only SRE debugging agent for the rewaatech-mims integrations platform.

## Mission
Investigate production incidents involving Zid, Salla, Bonat, or Grubtech integrations and produce a structured Root Cause Analysis (RCA) report.

## Skills & Workflow

Execute the following skills in order for each investigation:

1. **sre-jira-triage** — Extract structured facts from the Jira ticket (symptom, integration, onset time, links). Output → Section 2.1.
2. **sre-datadog-logs-traces** — Pull ERROR/WARN logs and distributed traces for the affected integration, anchored to the onset timestamp. Output → Section 2.2.
3. **sre-datadog-metrics** — Query error rate, latency (p50/p95/p99), and queue depth for anomalies in the onset window. Output → Section 2.3.
4. **sre-api-contract-check** — Verify the current third-party API contract (endpoints, schema, auth, pagination). Output → Section 2.4.
5. **sre-integrations-navigator** — Locate the relevant handler, mapper, and error-handling logic in the integrations codebase. Output → Section 2.5.
6. **sre-rca-synthesis** — Cross-correlate all evidence using the synthesis matrix to identify the root cause category. Output → Sections 1.3 & 3.
7. **sre-write-rca-report** — Assemble the final Markdown RCA document and write it to `~/ai-docs/debugging/[ISSUE-NUMBER].md`.

## Constraints

- **Never** create, edit, transition, or comment on Jira issues.
- **Never** create or modify Datadog monitors, dashboards, notebooks, or log pipelines.
- **Never** modify any source code in the repository.
- **Never** guess or fabricate log entries, metric values, or API specs — only report what tools return.
- If a tool returns no data for a section, record "No evidence found" and continue.

## Input

Provide a Jira ticket number (e.g., `MIMS-55317`) to begin the investigation.
If you also have a suspected integration name or onset timestamp, include those to accelerate the Datadog queries.
"""

_PROVIDER_NAME = "Anthropic"
_TOKEN_NAME = "anthropic-api-key"
_DEFAULT_MODEL = "claude-opus-4-5"

# ---------------------------------------------------------------------------
# MCP Servers
# ---------------------------------------------------------------------------

# Only list tools that are safe and read-only for each server.
# Empty list = all tools allowed (Zid/Salla are docs-only, inherently read-only).
_DATADOG_ALLOWED_TOOLS = [
    "analyze_datadog_logs",
    "search_datadog_logs",
    "search_datadog_metrics",
    "get_datadog_metric",
    "get_datadog_metric_context",
    "search_datadog_spans",
    "aggregate_spans",
    "get_datadog_trace",
    "search_datadog_services",
    "search_datadog_service_dependencies",
    "search_datadog_events",
    "aggregate_events",
    "search_datadog_incidents",
    "get_datadog_incident",
    "search_datadog_hosts",
    "search_datadog_monitors",
    "search_datadog_dashboards",
    "search_datadog_notebooks",
    "get_datadog_notebook",
    "search_datadog_rum_events",
    "aggregate_rum_events",
    "submit_mcp_feedback",
]

_ATLASSIAN_ALLOWED_TOOLS = [
    "atlassianUserInfo",
    "getAccessibleAtlassianResources",
    "fetchAtlassian",
    "searchAtlassian",
    "getVisibleJiraProjects",
    "getJiraProjectIssueTypesMetadata",
    "getJiraIssueTypeMetaWithFields",
    "getJiraIssue",
    "getJiraIssueRemoteIssueLinks",
    "getIssueLinkTypes",
    "getTransitionsForJiraIssue",
    "searchJiraIssuesUsingJql",
    "lookupJiraAccountId",
    "getConfluenceSpaces",
    "getPagesInConfluenceSpace",
    "getConfluencePage",
    "getConfluencePageDescendants",
    "getConfluencePageFooterComments",
    "getConfluencePageInlineComments",
    "getConfluenceCommentChildren",
    "searchConfluenceUsingCql",
]

_MCP_SERVERS: list[dict] = [
    {
        "name": "datadog-mcp",
        "transport_type": "http",
        "connection_config": {
            "url": "https://mcp.datadoghq.com",
            "headers": {
                "DD-API-KEY": "{{token:datadog-api-key}}",
                "DD-APPLICATION-KEY": "{{token:datadog-app-key}}",
            },
        },
        "allowed_tools": _DATADOG_ALLOWED_TOOLS,
        "tags": ["sre", "datadog"],
    },
    {
        "name": "jira-mcp",
        "transport_type": "stdio",
        "connection_config": {
            "command": "uvx",
            "args": ["mcp-atlassian"],
            "env": {
                "JIRA_URL": "{{token:jira-url}}",
                "JIRA_USERNAME": "{{token:jira-email}}",
                "JIRA_API_TOKEN": "{{token:jira-api-token}}",
            },
        },
        "allowed_tools": _ATLASSIAN_ALLOWED_TOOLS,
        "tags": ["sre", "jira", "atlassian"],
    },
    {
        "name": "zid-open-apis",
        "transport_type": "stdio",
        "connection_config": {
            "command": "npx",
            "args": ["-y", "zid-open-apis-mcp"],
        },
        "allowed_tools": [],  # all tools — docs server is read-only
        "tags": ["sre", "zid", "api-docs"],
    },
    {
        "name": "salla-docs-mcp",
        "transport_type": "stdio",
        "connection_config": {
            "command": "npx",
            "args": ["-y", "apidog-mcp-server@latest", "--site-id=451700"],
        },
        "allowed_tools": [],  # all tools — docs server is read-only
        "tags": ["sre", "salla", "api-docs"],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(github_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {github_token}", "Content-Type": "application/json"}


def _post(client: httpx.Client, url: str, payload: dict) -> dict:
    r = client.post(url, json=payload)
    r.raise_for_status()
    return r.json()


def _get(client: httpx.Client, url: str) -> list | dict:
    r = client.get(url)
    r.raise_for_status()
    return r.json()


def _existing_by_name(items: list[dict], name: str) -> dict | None:
    return next((i for i in items if i.get("name") == name), None)


# ---------------------------------------------------------------------------
# Provisioning steps
# ---------------------------------------------------------------------------


def seed_skills(client: httpx.Client, base: str) -> dict[str, str]:
    """Create skills and return a mapping of name → id."""
    existing: list[dict] = _get(client, f"{base}/api/skills")  # type: ignore[assignment]
    existing_names = {s["name"] for s in existing}
    skill_ids: dict[str, str] = {s["name"]: s["id"] for s in existing}

    for skill in _SKILLS:
        if skill["name"] in existing_names:
            print(f"  ⏭  Skill '{skill['name']}' already exists — skipping")
        else:
            created = _post(client, f"{base}/api/skills", skill)
            skill_ids[skill["name"]] = created["id"]
            print(f"  ✅ Skill '{skill['name']}' created (id={created['id']})")

    return skill_ids


def seed_token(client: httpx.Client, base: str, anthropic_key: str) -> None:
    """Store the Anthropic API key in the token vault."""
    existing: list[dict] = _get(client, f"{base}/api/tokens")  # type: ignore[assignment]
    if _existing_by_name(existing, _TOKEN_NAME):
        print(f"  ⏭  Token '{_TOKEN_NAME}' already exists — skipping")
        return
    _post(client, f"{base}/api/tokens", {"name": _TOKEN_NAME, "value": anthropic_key, "description": "Anthropic API key for hero-mechanic agent"})
    print(f"  ✅ Token '{_TOKEN_NAME}' created")


def seed_provider(client: httpx.Client, base: str) -> str | None:
    """Create the Anthropic provider and return its ID."""
    existing: list[dict] = _get(client, f"{base}/api/providers")  # type: ignore[assignment]
    found = _existing_by_name(existing, _PROVIDER_NAME)
    if found:
        print(f"  ⏭  Provider '{_PROVIDER_NAME}' already exists (id={found['id']}) — skipping")
        return found["id"]
    created = _post(
        client,
        f"{base}/api/providers",
        {
            "name": _PROVIDER_NAME,
            "provider_type": "anthropic",
            "api_key_token_name": _TOKEN_NAME,
            "description": "Anthropic Claude provider for SRE hero-mechanic agent",
        },
    )
    print(f"  ✅ Provider '{_PROVIDER_NAME}' created (id={created['id']})")
    return created["id"]


def seed_agent(client: httpx.Client, base: str, provider_id: str | None, mcp_server_ids: list[str]) -> None:
    """Create the hero-mechanic agent."""
    existing: list[dict] = _get(client, f"{base}/api/agents")  # type: ignore[assignment]
    found = _existing_by_name(existing, _AGENT_NAME)
    if found:
        print(f"  ⏭  Agent '{_AGENT_NAME}' already exists (id={found['id']}) — skipping")
        return
    payload: dict = {
        "name": _AGENT_NAME,
        "description": (
            "Read-only SRE debugging agent. Investigates TSP/Zid/Salla/Bonat incidents "
            "using Jira, Datadog, and API docs, then writes a structured RCA report. "
            "Never modifies Jira, Datadog, or source code."
        ),
        "system_prompt": _SYSTEM_PROMPT,
        "model": _DEFAULT_MODEL,
        "builtin_tools": [],
        "mcp_server_ids": mcp_server_ids,
    }
    if provider_id:
        payload["provider_id"] = provider_id
    created = _post(client, f"{base}/api/agents", payload)
    print(f"  ✅ Agent '{_AGENT_NAME}' created (id={created['id']})")


def seed_mcp_servers(client: httpx.Client, base: str) -> list[str]:
    """Create or update MCP servers and return their IDs in definition order."""
    existing: list[dict] = _get(client, f"{base}/api/mcps")  # type: ignore[assignment]
    id_map: dict[str, str] = {s["name"]: s["id"] for s in existing}
    config_map: dict[str, dict] = {s["name"]: s for s in existing}

    for server in _MCP_SERVERS:
        name = server["name"]
        if name in id_map:
            # Always PUT the latest config so connection_config/allowed_tools stay current
            r = client.put(f"{base}/api/mcps/{id_map[name]}", json=server)
            r.raise_for_status()
            print(f"  🔄 MCP server '{name}' updated (id={id_map[name]})")
        else:
            created = _post(client, f"{base}/api/mcps", server)
            id_map[name] = created["id"]
            print(f"  ✅ MCP server '{name}' created (id={created['id']})")

    return [id_map[m["name"]] for m in _MCP_SERVERS if m["name"] in id_map]


def update_agent_mcps(client: httpx.Client, base: str, mcp_server_ids: list[str]) -> None:
    """Patch an already-existing hero-mechanic agent with the MCP server IDs."""
    existing: list[dict] = _get(client, f"{base}/api/agents")  # type: ignore[assignment]
    found = _existing_by_name(existing, _AGENT_NAME)
    if not found:
        return  # agent doesn't exist yet — seed_agent will handle it
    current_ids: list[str] = found.get("mcp_server_ids") or []
    new_ids = list(dict.fromkeys(current_ids + mcp_server_ids))  # deduplicate, preserve order
    if set(new_ids) == set(current_ids):
        print(f"  ⏭  Agent '{_AGENT_NAME}' already has all MCP servers — skipping update")
        return
    r = client.put(f"{base}/api/agents/{found['id']}", json={"mcp_server_ids": new_ids})
    r.raise_for_status()
    print(f"  ✅ Agent '{_AGENT_NAME}' updated with {len(mcp_server_ids)} MCP server(s)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision SRE skills and hero-mechanic agent")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL (default: http://localhost:8000)")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub PAT for API auth (or set GITHUB_TOKEN env var)")
    parser.add_argument("--anthropic-key", default=os.environ.get("ANTHROPIC_API_KEY"), help="Anthropic API key (or set ANTHROPIC_API_KEY env var). Omit to skip provider creation.")
    args = parser.parse_args()

    if not args.github_token:
        print("ERROR: --github-token or GITHUB_TOKEN env var is required", file=sys.stderr)
        sys.exit(1)

    client = httpx.Client(headers=_headers(args.github_token), timeout=30)

    print("\n── SRE Skills ──────────────────────────────────────────")
    seed_skills(client, args.base_url)

    provider_id: str | None = None
    if args.anthropic_key:
        print("\n── Anthropic Token & Provider ──────────────────────────")
        seed_token(client, args.base_url, args.anthropic_key)
        provider_id = seed_provider(client, args.base_url)
    else:
        print("\n⚠  --anthropic-key not provided — skipping provider creation")
        print("   Agent will be created without an Anthropic provider.")
        print("   Re-run with --anthropic-key to attach a provider later.")

    print("\n── MCP Servers ─────────────────────────────────────────")
    mcp_server_ids = seed_mcp_servers(client, args.base_url)

    print("\n── SRE Agent ───────────────────────────────────────────")
    seed_agent(client, args.base_url, provider_id, mcp_server_ids)
    # If the agent already existed (from a previous run), patch its MCP server list
    update_agent_mcps(client, args.base_url, mcp_server_ids)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
