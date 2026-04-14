# Configuration

All configuration is managed through environment variables. Pydantic Settings loads them from `.env` automatically.

---

## Core Settings

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `copilot_agent_hub` | Database name |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL for broker/backend + pub/sub |
| `DEFAULT_MODEL` | `gpt-4.1` | Default model for new workflows |
| `DEFAULT_MAX_TURNS` | `5` | Default max tool-call turns per workflow |
| `SESSION_TIMEOUT` | `300` | SDK session timeout in seconds |

---

## Authentication Tokens

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | Server-level GitHub PAT (requires `copilot` scope) |
| `TOKEN_ENCRYPTION_KEY` | — | Fernet key for encrypting stored tokens |

!!! warning
    `GITHUB_TOKEN` is required. Without it, agent sessions cannot authenticate against the Copilot SDK.

---

## Integration Tokens

These are optional and only needed if you use the corresponding MCP servers:

| Variable | Default | Description |
|---|---|---|
| `NOTION_TOKEN` | — | Notion integration token |
| `SLACK_BOT_TOKEN` | — | Slack bot token |
| `DD_API_KEY` | — | Datadog API key |
| `DD_APP_KEY` | — | Datadog App key |
| `DD_SITE` | `datadoghq.com` | Datadog site |
| `ATLASSIAN_API_TOKEN` | — | Atlassian API token |
| `ATLASSIAN_EMAIL` | — | Atlassian account email |
| `ATLASSIAN_URL` | — | Atlassian site URL |

---

## Setting Up

=== "Docker Compose"

    ```bash
    cp .env.example .env
    # Edit .env with your values
    docker-compose up --build
    ```

=== "Bare Metal"

    ```bash
    export MONGO_URI=mongodb://localhost:27017
    export REDIS_URL=redis://localhost:6379/0
    export GITHUB_TOKEN="ghp_your_token_here"
    ```

    Or use a `.env` file — Pydantic Settings loads it automatically.
