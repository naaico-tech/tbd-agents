---
icon: material/key-variant
---

# BYOK Providers

Bring Your Own Key (BYOK) lets you run agents against **external LLM providers** — OpenAI, Azure OpenAI, Anthropic, Google ADK, or a custom endpoint — using your own API keys. TBD Agents handles streaming, retries, context management, and tool orchestration identically to the built-in Copilot SDK path where runtime support exists.

## Supported Provider Types

| Type | Description |
|---|---|
| `openai` | OpenAI API (`api.openai.com`) or any compatible proxy |
| `azure_openai` | Azure OpenAI Service with deployment-based routing |
| `anthropic` | Anthropic Claude via the Claude Agent SDK (`beta.agents/sessions`) |
| `google_adk` | Stores Google ADK configuration for Gemini API keys and optional Vertex AI settings |
| `github_copilot` | Overrides the default GitHub token with a stored PAT |
| `custom` | Any OpenAI-compatible endpoint — set `base_url` |

## Quick Setup

### 1. Store your API key

```bash
curl -X POST http://localhost:8000/api/tokens \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "openai-key", "value": "sk-..."}'
```

### 2. Register the provider

```bash
curl -X POST http://localhost:8000/api/providers \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-openai",
    "provider_type": "openai",
    "api_key_token_name": "openai-key"
  }'
```

### 3. Attach to an agent

```bash
curl -X PUT http://localhost:8000/api/agents/{agent_id} \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider_id": "<provider-id>"}'
```

That's it — workflows created with this agent now route to OpenAI.

## Google ADK

Google ADK providers can now be configured on the provider surface. Use
`api_key_token_name` for a Gemini API key, and optionally switch the provider into
Vertex AI mode with explicit project/location metadata:

```json
{
  "name": "google-adk-gemini",
  "provider_type": "google_adk",
  "api_key_token_name": "gemini-api-key",
  "google_use_vertex_ai": true,
  "google_cloud_project": "my-gcp-project",
  "google_cloud_location": "us-central1"
}
```

When `google_use_vertex_ai` is enabled, the provider stores the values that map cleanly to `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`.

!!! note
    `google_adk` providers now support:

    - workflow execution through the in-process Google ADK runtime
    - agent chat through the app's chat surface
    - `/api/models?provider_id=<google-adk-provider>` model listing

    Gemini API providers require the provider's stored token to contain a Gemini API
    key. Vertex AI providers can run keyless when `google_use_vertex_ai=true` and
    both `google_cloud_project` and `google_cloud_location` are set.

## Azure OpenAI

Azure deployments require a `base_url` and either an explicit `azure_deployment` or the workflow's model name:

```json
{
  "name": "azure-gpt4o",
  "provider_type": "azure_openai",
  "api_key_token_name": "azure-key",
  "base_url": "https://myresource.openai.azure.com",
  "azure_deployment": "gpt-4o",
  "azure_api_version": "2024-12-01-preview"
}
```

The engine constructs the correct URL:

```
{base_url}/openai/deployments/{deployment}/chat/completions?api-version={version}
```

If `azure_deployment` is not set, the workflow's `model` field is used as the deployment name.

## Features

### Streaming

OpenAI, Azure OpenAI, and custom OpenAI-compatible providers stream responses via SSE. Anthropic providers stream via Claude Agent SDK events. In both cases, content deltas are published in real-time to the same event bus used by the Copilot SDK path — clients receive `message_delta` events identical to those from the built-in path.

### Retry & Error Handling

Transient errors are retried automatically with exponential backoff:

- **Retryable status codes:** 429, 500, 502, 503, 504
- **Retryable exceptions:** connection errors, read/write timeouts
- **Max retries:** 3 retries / 4 total attempts, with exponential backoff between retries (1s, 2s, 4s)
- **Retry-After:** Honoured when the provider sends the header

Non-retryable errors (e.g. 401, 403) fail immediately.

### Context Compaction

When accumulated input tokens exceed **80% of the 128k context window**, the engine automatically compacts the conversation:

1. Keeps the system prompt and original user message
2. Drops intermediate tool call/result exchanges
3. Inserts a compaction marker for the model
4. Retains the last 6 messages for continuity

This prevents context overflow during long agentic loops.

### Usage Tracking

Every BYOK execution records:

| Metric | Source |
|---|---|
| `prompt_tokens` | `usage.prompt_tokens` |
| `completion_tokens` | `usage.completion_tokens` |
| `cached_tokens` | `usage.prompt_tokens_details.cached_tokens` |
| `cost` | `usage.cost` (if provider returns it) |

All metrics are exposed as Prometheus histograms (`cache_read`, `cache_write`, `cost_dollars_total`, `tool_calls_per_task`).

### Progress Tracking

When an agent calls `manage_todo_list`, the engine parses the todo items and updates the task execution's progress — the same behaviour as the Copilot SDK path.

### Tool Calling

BYOK providers use the **OpenAI function-calling format**. All MCP tools configured on the agent are converted to OpenAI tool definitions and passed to the model. The engine loops:

1. Send messages + tools to the provider
2. If the model returns `tool_calls`, execute each via MCP
3. Append results and repeat
4. When the model responds without tool calls (or hits `max_turns`), return the final answer

## Comparison with Copilot SDK Path

| Feature | Copilot SDK | BYOK Custom |
|---|---|---|
| Streaming | ✅ SDK events | ✅ SSE chunks |
| Tool calling | ✅ SDK-managed | ✅ OpenAI function-calling loop |
| Context management | ✅ SDK-managed | ✅ Auto-compaction at 80% |
| Retry logic | ✅ SDK-managed | ✅ Exponential backoff |
| Usage tracking | ✅ SDK events | ✅ Response usage fields |
| Progress tracking | ✅ SDK events | ✅ `manage_todo_list` parsing |
| Azure support | ❌ | ✅ Deployment-based routing |
| Model freedom | GitHub models | Any OpenAI-compatible |
