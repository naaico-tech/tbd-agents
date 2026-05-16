# Shopify Agent — MCP Server Configs

The first-party Shopify plugin (`app/plugins/shopify.py`) covers Admin GraphQL
read + write. Slack is delivered via the Slack plugin. Everything else that
the Shopify Agent needs and that does **not** have a TBD-Agents plugin lives
here as an MCP server.

| File | Why an MCP (not a plugin) |
|---|---|
| `shopify-admin-mcp.json` | Official Shopify dev MCP server — exposes docs/search tools beyond Admin GraphQL. Optional companion to the plugin. |
| `gorgias-mcp.json`       | No first-party plugin for the helpdesk. |

## Registering

```bash
curl -X POST http://localhost:8000/api/mcps \
  -H "Authorization: Bearer $TBD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @gorgias-mcp.json
```

## Token placeholders

| Placeholder | Holds |
|---|---|
| `{{token:shopify-admin-api-token}}` | Shopify Admin API access token |
| `{{token:shopify-store-domain}}` | `your-store.myshopify.com` |
| `{{token:gorgias-api-key}}` | Gorgias API key |
| `{{token:gorgias-subdomain}}` | Gorgias subdomain |

## Agent tag binding

```yaml
mcp_server_tags: [shopify, ecommerce, ops]
```
