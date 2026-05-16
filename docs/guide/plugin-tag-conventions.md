# Plugin & MCP Tag Conventions

Tags are the glue between **agents** and the **tools** they pick up at runtime.
An agent's `mcp_server_tags` (and the equivalent custom-tool tag filters) are
matched against the `tags` declared by each plugin or MCP server. Consistent
tagging is what lets a new plugin get auto-discovered by the right agents
without code changes.

## Tag Schema

Every plugin and MCP server should declare tags in this order:

```
[<product>, <domain>, <category...>, <capability...>, <role...>]
```

| Slot | Purpose | Examples |
|---|---|---|
| **product** | The concrete vendor/product name (lowercase, underscored if multi-word). | `shopify`, `datadog`, `ga4`, `google_analytics`, `pagerduty`, `meta_ads` |
| **domain** | High-level business or technical domain. | `ecommerce`, `observability`, `analytics`, `marketing`, `infrastructure` |
| **category** | One or more sub-areas inside the domain. | `catalog`, `orders`, `metrics`, `logs`, `incident`, `web-analytics`, `paid-search`, `social-ads` |
| **capability** | What the tool can *do*. | `read`, `write` (omit `write` for read-only plugins) |
| **role** | The agent role/persona that should pick this tool up. | `sre`, `ops`, `marketing` |

### Rules

1. **Product first, always.** Agents that need a specific product use
   `mcp_server_tags: [<product>]` and expect a guaranteed match.
2. **Use existing values before inventing new ones.** Pick from the tables
   below where possible.
3. **Lowercase, hyphen for multi-word values within a tag, underscore between
   words in product identifiers** (`web-analytics` ✓, `google_analytics` ✓).
4. **`read` is always present.** `write` is added only when the plugin can
   mutate external state.
5. **Role tags are additive.** A plugin may be useful to multiple roles
   (e.g. `kubernetes` is tagged `sre`, but `observability` makes it discoverable
   by SRE-adjacent agents too).
6. **MCP server tags mirror plugin tags.** The same convention applies to JSON
   payloads in `examples/mcp-servers/<agent>/` so an agent's
   `mcp_server_tags` resolves both bundled plugins and remote MCP servers.

## Current Plugins

| Plugin | File | Tags |
|---|---|---|
| Shopify | `app/plugins/shopify.py` | `shopify, ecommerce, ops, catalog, orders, inventory, read, write` |
| Datadog | `app/plugins/datadog.py` | `datadog, observability, metrics, logs, monitors, sre` |
| PagerDuty | `app/plugins/pagerduty.py` | `pagerduty, incident, oncall, alerting, ticketing, sre` |
| Kubernetes | `app/plugins/kubernetes.py` | `kubernetes, k8s, infrastructure, observability, sre, read` |
| Google Analytics (GA4) | `app/plugins/google_analytics.py` | `ga4, google_analytics, analytics, web-analytics, marketing, read` |
| Google Ads | `app/plugins/google_ads.py` | `google_ads, ads, paid-search, analytics, marketing, read` |
| Meta Ads | `app/plugins/meta_ads.py` | `meta_ads, facebook_ads, instagram_ads, ads, social-ads, analytics, marketing, read` |
| Google Slides | `app/plugins/google_slides.py` | `google, google_slides, slides, workspace, reporting, marketing, read, write` |
| Google Search Console | `app/plugins/google_search_console.py` | `google, search_console, gsc, seo, web-analytics, marketing, read` |

## Agent → Tag Mapping

Recommended `mcp_server_tags` for the agents whose plans live in `docs/plans/`:

### Shopify Agent (operational)
```yaml
mcp_server_tags: [shopify, ecommerce, ops]
```
Resolves: `shopify` (bundled plugin) + MCP servers in
`examples/mcp-servers/shopify-agent/` (Shopify Admin dev MCP, Gorgias).

### SRE Agent
```yaml
mcp_server_tags: [datadog, pagerduty, kubernetes, observability, sre]
```
Resolves: `datadog`, `pagerduty`, `kubernetes` (bundled plugins) + MCP servers
in `examples/mcp-servers/sre-agent/` (GitHub, AWS, GCP, Prometheus, Jira).

### Marketing Analyst
```yaml
mcp_server_tags: [ga4, google_ads, meta_ads, marketing, analytics, ads]
```
Resolves: `google_analytics`, `google_ads`, `meta_ads`, `google_slides`,
`google_search_console` (bundled plugins, including the Google Workspace
service-account ones) + MCP servers in
`examples/mcp-servers/marketing-analyst/` (LinkedIn Ads, TikTok Ads).

> **Rule of thumb:** if a capability is already covered by a custom-tool
> plugin (Slack, Notion, BigQuery, Google Sheets/Slides/Search Console,
> Google Analytics, Google Ads, Meta Ads, etc.), **do not** register a
> duplicate MCP server. Extend the plugin instead.

## Adding a New Plugin or MCP

1. Pick the **product** name and confirm it's not already taken.
2. Choose the **domain** and 1–3 **category** tags that match an existing agent's
   `mcp_server_tags`, otherwise the plugin will not be auto-discovered.
3. Add **capability** (`read` and/or `write`).
4. Add **role** tags for any persona that should see it.
5. Register the plugin in `app/plugins.yaml` (for bundled plugins) or POST the
   JSON payload to `/api/mcps` (for MCP servers).

> Skills, agent base prompts, and guardrails are **proprietary** and must be
> created through the dashboard / API at deploy time; they are intentionally
> not part of this repo.
