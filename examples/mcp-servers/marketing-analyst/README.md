# Marketing Analyst — MCP Server Configs

Only **remote** marketing platforms live here. Anything that ships as a
TBD-Agents **plugin** (BigQuery, GA4, Google Ads, Meta Ads, Google Sheets,
Google Slides, Google Search Console, Notion, Slack) is registered through
`app/plugins.yaml`, not as an MCP server. The plugins authenticate with a
Google service-account key (`{{token:...}}`-resolved) wherever possible.

This directory currently registers:

| File | Why an MCP (not a plugin) |
|---|---|
| `linkedin-ads-mcp.json` | No first-party plugin; use the community MCP server. |
| `tiktok-ads-mcp.json`   | No first-party plugin; use the community MCP server. |

## Registering

```bash
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $TBD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @linkedin-ads-mcp.json
```

## Token placeholders

| Placeholder | Holds |
|---|---|
| `{{token:linkedin-ads-access-token}}` | LinkedIn Marketing API access token |
| `{{token:tiktok-ads-access-token}}` | TikTok Ads API access token |
| `{{token:tiktok-ads-app-id}}` | TikTok Ads app ID |
| `{{token:tiktok-ads-app-secret}}` | TikTok Ads app secret |

## Agent tag binding

The Marketing Analyst's `mcp_server_tags` resolve both bundled plugins and the
MCP servers here:

```yaml
mcp_server_tags: [ga4, google_ads, meta_ads, marketing, analytics, ads]
```

`linkedin_ads` and `tiktok_ads` carry the `ads, social-ads, marketing` tags
so the same agent picks them up automatically.
