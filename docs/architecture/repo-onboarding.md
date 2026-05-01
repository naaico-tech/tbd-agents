# Code Repository Onboarding

This page documents how a code repository is registered, synced, and indexed — and how **GitNexus** provides code-intelligence on top.

---

## Onboarding Flow

```mermaid
flowchart TD
    A([User / Frontend]) -->|"POST /api/code-repositories\n{name, repo_url, branch, token_name, tags}"| B

    B["MongoDB: CodeRepository\nstatus = REGISTERED"]

    B --> C["POST /{repo_id}/sync"]
    C --> D["code_repository_manager.sync()\nstatus → SYNCING"]

    D --> E{Local .git exists?}
    E -->|No| F["git clone --depth 1 --branch branch\ninto /repos/sha256_hash/"]
    E -->|Yes| G["git fetch --depth 1 origin branch\ngit checkout FETCH_HEAD"]

    F --> H["Capture HEAD commit SHA"]
    G --> H

    H -->|Success| I["MongoDB: status = SYNCED\nlocal_path · last_commit_sha set"]
    H -->|Failure| ERR1["MongoDB: status = ERROR\nlast_error saved"]

    I --> J["POST /{repo_id}/index"]
    J --> K{GITNEXUS_URL configured?}

    K -->|No| SKIP["Return: gitnexus_unavailable"]

    K -->|Yes| L["Translate path:\n/repos/hash → /workspace/hash\nPOST {gitnexus_url}/api/analyze"]

    L -->|202 Accepted| M["MongoDB: status = INDEXING\ngitnexus_job_id saved"]
    L -->|Error / timeout| ERR2["MongoDB: status = ERROR"]

    M --> N["Poll: GET /{repo_id}/index/status"]
    N --> O["GET {gitnexus_url}/api/analyze/{job_id}"]

    O -->|in_progress| N
    O -->|complete| P["MongoDB: status = INDEXED\nlast_indexed_at set"]
    O -->|failed| ERR3["MongoDB: status = ERROR"]

    P --> Q(["Agent uses GitNexus MCP\nto search code"])

    style ERR1 fill:#ef4444,color:#fff
    style ERR2 fill:#ef4444,color:#fff
    style ERR3 fill:#ef4444,color:#fff
    style SKIP fill:#f59e0b,color:#fff
    style Q fill:#22c55e,color:#fff
```

---

## Architecture

```mermaid
graph TB
    subgraph Client["👤 Client"]
        UI["Flutter Frontend"]
    end

    subgraph API["🚀 TBD Agents — FastAPI"]
        ROUTE["REST API\n/api/code-repositories"]
        CRM["CodeRepositoryManager\n• sync()  — clone / fetch\n• index() — call GitNexus\n• check_index_status()\n• resolve_for_workflow()"]
        SEEDER["gitnexus_seeder\n(startup: auto-register MCP server)"]
    end

    subgraph Workers["⚙️ Celery Workers"]
        SYNC_W["run_sync_repository_job\nqueue: default"]
        IDX_ORC["run_index_repository_job\nqueue: indexing\n(orchestrator)"]
        IDX_SH["index_shard × N\nqueue: embeddings"]
        FINALIZE["finalize_index_job\n(chord callback)"]
        REDIS["Redis\n(broker · progress counters · STM)"]
    end

    subgraph Storage["💾 Storage"]
        MONGO[("MongoDB\nCodeRepository · IndexJob · IndexedFile")]
        DISK[("Local Disk  /repos/hash/\nshared volume")]
    end

    subgraph GN["🔬 GitNexus"]
        GN_REST["REST API\nPOST /api/analyze\nGET  /api/analyze/{id}"]
        GN_MCP["MCP Server  /api/mcp\n(query / search tool)"]
    end

    GIT["☁️ Git Hosting\nGitHub · GitLab · Bitbucket"]

    UI -->|HTTP REST| ROUTE
    ROUTE --> CRM
    ROUTE -->|read / write| MONGO
    SEEDER -->|"upsert McpServer on startup\n(name: gitnexus)"| MONGO

    CRM -->|status updates| MONGO
    CRM -->|"clone / fetch (inline)"| DISK
    CRM -->|POST /api/analyze| GN_REST
    CRM -->|GET /api/analyze/id| GN_REST
    CRM --> GIT

    ROUTE -.->|enqueue worker-only sync| SYNC_W
    SYNC_W --> GIT
    SYNC_W --> DISK
    SYNC_W -->|status update| MONGO

    ROUTE -.->|enqueue IndexJob| IDX_ORC
    IDX_ORC --> DISK
    IDX_ORC -->|chord fan-out| IDX_SH
    IDX_SH --> FINALIZE
    IDX_SH -->|progress counters| REDIS
    FINALIZE -->|finalize repo summary| MONGO

    GN_REST -->|reads source files| DISK
    GN_MCP -.->|"code search\n(attached to Workflows)"| ROUTE
```

---

## GitNexus Role Summary

| Stage | What happens |
|---|---|
| **App startup** | `gitnexus_seeder` upserts a `McpServer` record (name `gitnexus`, transport HTTP) pointing at `{GITNEXUS_URL}/api/mcp`. |
| **Index trigger** | `POST /{repo_id}/index` → `CodeRepositoryManager.index()` posts `{"path": "/workspace/<hash>"}` to `{GITNEXUS_URL}/api/analyze`. The repo hash directory is shared between TBD Agents and GitNexus via a Docker volume. |
| **Progress polling** | `GET /{repo_id}/index/status` proxies `GET {GITNEXUS_URL}/api/analyze/{job_id}` and drives the repo status to `INDEXED` (or `ERROR`). |
| **Code search** | Agents attach the `gitnexus` MCP server to their Workflows. The MCP `query` tool is the primary code-search interface; the internal Qdrant embedding pipeline is now a compatibility stub. |
