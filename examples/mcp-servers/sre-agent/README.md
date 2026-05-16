# SRE Agent — MCP Server Configs

Datadog, PagerDuty, Kubernetes, and Slack ship as TBD-Agents plugins. The
remaining cloud + repo tools the SRE Agent needs are registered here as MCP
servers (no first-party plugin yet).

| File | Why an MCP |
|---|---|
| `github-mcp.json`     | Repo browsing / PR diffs via official GitHub MCP. |
| `aws-mcp.json`        | Cross-service AWS read (EC2, RDS, S3). |
| `gcp-mcp.json`        | Cross-service GCP read (GCE, GKE, CloudSQL). |
| `prometheus-mcp.json` | PromQL queries against a Prometheus endpoint. |
| `jira-mcp.json`       | Incident ticketing handoff. |

## Registering

```bash
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $TBD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @github-mcp.json
```

## Token placeholders

| Placeholder | Holds |
|---|---|
| `{{token:github-personal-access-token}}` | GitHub PAT (read-only recommended) |
| `{{token:aws-access-key-id}}` / `{{token:aws-secret-access-key}}` | AWS read-only IAM credentials |
| `{{token:gcp-service-account-json}}` | GCP service-account JSON (viewer roles) |
| `{{token:prometheus-url}}` / `{{token:prometheus-bearer-token}}` | Prometheus endpoint + auth |
| `{{token:jira-base-url}}` / `{{token:jira-email}}` / `{{token:jira-api-token}}` | Jira Cloud auth |

## Agent tag binding

```yaml
mcp_server_tags: [datadog, pagerduty, kubernetes, observability, sre]
```
