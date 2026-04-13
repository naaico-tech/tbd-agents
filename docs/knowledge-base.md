```
██╗  ██╗███╗   ██╗ ██████╗ ██╗    ██╗██╗     ███████╗██████╗  ██████╗ ███████╗
██║ ██╔╝████╗  ██║██╔═══██╗██║    ██║██║     ██╔════╝██╔══██╗██╔════╝ ██╔════╝
█████╔╝ ██╔██╗ ██║██║   ██║██║ █╗ ██║██║     █████╗  ██║  ██║██║  ███╗█████╗
██╔═██╗ ██║╚██╗██║██║   ██║██║███╗██║██║     ██╔══╝  ██║  ██║██║   ██║██╔══╝
██║  ██╗██║ ╚████║╚██████╔╝╚███╔███╔╝███████╗███████╗██████╔╝╚██████╔╝███████╗
╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝  ╚══╝╚══╝ ╚══════╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝
                         ██████╗  █████╗ ███████╗███████╗███████╗
                         ██╔══██╗██╔══██╗██╔════╝██╔════╝██╔════╝
                         ██████╔╝███████║███████╗█████╗  ███████╗
                         ██╔══██╗██╔══██║╚════██║██╔══╝  ╚════██║
                         ██████╔╝██║  ██║███████║███████╗███████║
                         ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝
```

<p align="center"><sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub></p>

> 📚 Knowledge Bases let agents query a curated document corpus at runtime, injecting the most relevant chunks directly into the system prompt.

---

## 🎯 Problem Statement

Agents in TBD Agent rely on their **system prompt** and **skills** for domain knowledge.  Both are static — they are written once and never updated.  For knowledge that changes frequently (runbooks, API docs, internal policies, product catalogs) this creates a maintenance burden and a context-window cost: dumping all knowledge into the system prompt wastes tokens even when only a small fraction is relevant to the current task.

**Knowledge Bases solve this by:**

1. Storing document chunks in MongoDB alongside the rest of the system's state.
2. At run time, ranking all chunks against the user's prompt with **BM25** and injecting only the top-k most relevant ones.
3. Requiring **zero additional infrastructure** — no vector database, no embedding API, no GPU.

---

## 🏗️ Design Principles

```
┌──────────────────────────────────────────────────────────────────┐
│  ░░ DESIGN GOALS ░░                                              │
├──────────────────────────────────────────────────────────────────┤
│  Lightweight   — one pure-Python dependency (rank-bm25)          │
│  Scalable      — chunks live in MongoDB; stateless retrieval     │
│  Deployable    — works with existing docker-compose; no extras   │
│  Open source   — rank-bm25 (MIT), MongoDB (SSPL / free tier)     │
│  Upgradeable   — retriever has a single hook for vector search   │
└──────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ How It Works

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║  INGEST                                                          ║
║  ──────────────────────────────────────────────────────────      ║
║  POST /api/knowledge-bases                ─► KnowledgeBase       ║
║  POST /api/knowledge-bases/{id}/chunks    ─► KnowledgeChunk      ║
║      • content tokenised on write (lower-case word split)        ║
║      • tokens[] stored alongside content in MongoDB              ║
║                                                                  ║
║  ATTACH                                                          ║
║  ──────────────────────────────────────────────────────────      ║
║  POST /api/workflows  { knowledge_base_ids: ["<KB_ID>"] }        ║
║      • IDs stored on the Workflow document (like skill_ids)      ║
║                                                                  ║
║  RETRIEVE (at agent run time)                                    ║
║  ──────────────────────────────────────────────────────────      ║
║  1. load all KnowledgeChunks for the workflow's KB IDs           ║
║  2. score against user_prompt with BM25Okapi                     ║
║  3. inject top-5 chunks as <knowledge_context> into system prompt ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

### Retrieval Algorithm: BM25

**BM25** (Best Match 25) is the standard probabilistic text-ranking formula used by Elasticsearch, Solr, and most search engines.  It balances term frequency, inverse document frequency, and document length normalisation.

```
score(Q, D) = Σ IDF(q) · (tf(q,D) · (k₁+1)) / (tf(q,D) + k₁·(1 - b + b·|D|/avgdl))
```

Why BM25 over other options:

```
┌────────────────────┬───────────────┬────────────┬────────────┬───────────────┐
│  ░░ METHOD         │  ░░ QUALITY   │  ░░ INFRA  │  ░░ SPEED  │  ░░ DEPS      │
├────────────────────┼───────────────┼────────────┼────────────┼───────────────┤
│  BM25 (chosen)     │  Good         │  None      │  Fast      │  rank-bm25    │
│  Dense embeddings  │  Best         │  GPU/API   │  Moderate  │  fastembed    │
│  TF-IDF (sklearn)  │  Moderate     │  None      │  Fast      │  scikit-learn │
│  Full-text (Mongo) │  Basic        │  None      │  Fast      │  None (Atlas) │
│  Qdrant/Weaviate   │  Best         │  Extra svc │  Fast      │  qdrant-client│
└────────────────────┴───────────────┴────────────┴────────────┴───────────────┘
```

---

## 📐 Data Model

```
╔════════════════════════════════════════════════════╗
║                                                    ║
║  📚 KnowledgeBase                                  ║
║  ├── name        (unique label)                    ║
║  ├── description                                   ║
║  └── tags[]                                        ║
║                                                    ║
║  📄 KnowledgeChunk                                 ║
║  ├── knowledge_base_id  ──► KnowledgeBase          ║
║  ├── content            (raw text, any length)     ║
║  ├── tokens[]           (pre-tokenised for BM25)   ║
║  └── source             (attribution label)        ║
║                                                    ║
║  ⚙️ Workflow  (extended)                            ║
║  └── knowledge_base_ids[] ──► KnowledgeBase        ║
║                                                    ║
╚════════════════════════════════════════════════════╝
```

---

## 🔌 API Reference

### Knowledge Bases

```
 ┌────────────────────────────────────────────┬────────────────────────────┐
 │  ░░ ENDPOINT                               │  ░░ ACTION                 │
 ├────────────────────────────────────────────┼────────────────────────────┤
 │  POST   /api/knowledge-bases               │  Create a knowledge base   │
 │  GET    /api/knowledge-bases               │  List all knowledge bases  │
 │  GET    /api/knowledge-bases/{id}          │  Get one knowledge base    │
 │  PUT    /api/knowledge-bases/{id}          │  Update metadata           │
 │  DELETE /api/knowledge-bases/{id}          │  Delete KB + all chunks    │
 ├────────────────────────────────────────────┼────────────────────────────┤
 │  POST   /api/knowledge-bases/{id}/chunks   │  Add a chunk               │
 │  GET    /api/knowledge-bases/{id}/chunks   │  List chunks in a KB       │
 │  GET    /api/knowledge-bases/{id}/chunks/{chunk_id} │ Get one chunk     │
 │  PUT    /api/knowledge-bases/{id}/chunks/{chunk_id} │ Update a chunk    │
 │  DELETE /api/knowledge-bases/{id}/chunks/{chunk_id} │ Delete a chunk    │
 └────────────────────────────────────────────┴────────────────────────────┘
```

All endpoints require `Authorization: Bearer <GitHub PAT>`.

---

## 🚀 Quick Start

### 1 — Create a knowledge base

```bash
KB=$(curl -s -X POST http://localhost:8000/api/knowledge-bases \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "incident-runbooks",
    "description": "On-call runbooks for common production incidents",
    "tags": ["sre", "incidents"]
  }' | jq -r '.id')

echo "Created KB: $KB"
```

### 2 — Ingest document chunks

```bash
# Add a chunk manually
curl -X POST http://localhost:8000/api/knowledge-bases/$KB/chunks \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "## Database Connection Exhaustion\n\nSymptoms: high latency, 5xx errors on /api/* endpoints.\nStep 1: Check pg_stat_activity for blocked queries.\nStep 2: Restart the connection pool: kubectl rollout restart deploy/api.\nStep 3: If unresolved, scale the database read replicas.",
    "source": "runbooks/db-connection-exhaustion.md"
  }'

# Bulk-ingest a local Markdown file (500-char chunks, 50-char overlap)
python - <<'EOF'
import httpx, os, textwrap, json

TOKEN = os.environ["GITHUB_TOKEN"]
KB_ID = os.environ.get("KB_ID", "$KB")
BASE  = "http://localhost:8000"

with open("docs/runbooks/redis-failover.md") as f:
    text = f.read()

# Simple fixed-size chunking
chunk_size, overlap = 500, 50
chunks = []
i = 0
while i < len(text):
    chunks.append(text[i:i+chunk_size])
    i += chunk_size - overlap

for idx, chunk in enumerate(chunks):
    r = httpx.post(
        f"{BASE}/api/knowledge-bases/{KB_ID}/chunks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"content": chunk, "source": f"redis-failover.md § chunk-{idx}"},
    )
    r.raise_for_status()
    print(f"Inserted chunk {idx+1}/{len(chunks)}")
EOF
```

### 3 — Attach to a workflow

```bash
WF=$(curl -s -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"<AGENT_ID>\",
    \"knowledge_base_ids\": [\"$KB\"],
    \"model\": \"gpt-4.1\"
  }" | jq -r '.id')

# Send a prompt — top-5 relevant chunks are injected automatically
curl -X POST http://localhost:8000/api/workflows/$WF/prompt \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How do I fix a database connection exhaustion incident?"}'
```

---

## 🔩 System Prompt Integration

At run time, `_build_system_prompt` in `app/core/agent_engine.py` calls
`app/core/knowledge_retriever.retrieve()`, which:

1. Loads all `KnowledgeChunk` documents for the workflow's `knowledge_base_ids`.
2. Scores them against the current `user_prompt` with `BM25Okapi`.
3. Returns the top-5 chunks (≤ 4 000 chars) as an XML block.

The block is inserted **before** the execution policy directive:

```
<system_prompt>
  {agent.system_prompt}

  <skills>…</skills>           ← existing skills (if any)

  <knowledge_context>          ← injected by knowledge retriever
    <chunk source="runbooks/db-connection-exhaustion.md">
      ## Database Connection Exhaustion
      …
    </chunk>
    …
  </knowledge_context>

  <execution_policy>…</execution_policy>
</system_prompt>
```

---

## 📈 Scalability

```
┌──────────────────┬──────────────────────────────────────────────────┐
│  ░░ DIMENSION    │  ░░ BEHAVIOUR                                    │
├──────────────────┼──────────────────────────────────────────────────┤
│  Chunk count     │  BM25 scoring is O(n·q) where n = chunks,       │
│                  │  q = query terms. Up to ~10 000 chunks remains  │
│                  │  fast (< 50 ms on a single core).               │
├──────────────────┼──────────────────────────────────────────────────┤
│  Workers         │  Retrieval is stateless; each Celery worker      │
│                  │  loads chunks fresh per task from MongoDB.       │
├──────────────────┼──────────────────────────────────────────────────┤
│  MongoDB storage │  Each chunk is a small document; MongoDB handles │
│                  │  millions of small documents efficiently.        │
│                  │  Add a compound index on (knowledge_base_id)     │
│                  │  for faster chunk loading at scale.              │
├──────────────────┼──────────────────────────────────────────────────┤
│  Large corpora   │  For > 50 000 chunks, switch to the vector       │
│                  │  search upgrade path described below.            │
└──────────────────┴──────────────────────────────────────────────────┘
```

---

## 🔼 Upgrade Path: Vector Search

The retriever is designed to be swapped without changing the rest of the
system.  To enable dense vector retrieval:

### Option A — fastembed + in-process cosine similarity (no extra services)

```bash
pip install fastembed
```

Replace `_score_chunks` in `app/core/knowledge_retriever.py`:

```python
from fastembed import TextEmbedding
import numpy as np

_embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

def _embed(texts: list[str]) -> np.ndarray:
    return np.array(list(_embed_model.embed(texts)))

async def retrieve(knowledge_base_ids, query, top_k=5, max_chars=4000):
    chunks = await KnowledgeChunk.find(
        {"knowledge_base_id": {"$in": knowledge_base_ids}}
    ).to_list()
    if not chunks:
        return ""
    corpus_vecs = _embed([c.content for c in chunks])
    query_vec   = _embed([query])[0]
    scores = corpus_vecs @ query_vec / (
        np.linalg.norm(corpus_vecs, axis=1) * np.linalg.norm(query_vec) + 1e-9
    )
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    selected = [c for _, c in ranked[:top_k]]
    # … format as before …
```

Store pre-computed embeddings on `KnowledgeChunk.embedding: list[float]` to
avoid re-embedding the corpus on every call.

### Option B — Qdrant (dedicated vector database)

Add Qdrant to `docker-compose.yml`:

```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"
  volumes:
    - qdrant_data:/qdrant/storage
```

Then use `qdrant-client` for upsert/search:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(url="http://qdrant:6333")

# Index
client.upsert(collection_name="knowledge", points=[
    PointStruct(id=chunk_id, vector=embedding, payload={"kb_id": kb_id, "content": content})
])

# Query
results = client.search(collection_name="knowledge", query_vector=query_embedding, limit=5)
```

Qdrant scales to billions of vectors with HNSW approximate nearest-neighbour
search.  Use this when your knowledge corpus exceeds ~100 000 chunks.

---

## 🗃️ Recommended Chunking Strategies

```
┌──────────────────────┬───────────────────────────────────────────┐
│  ░░ STRATEGY         │  ░░ BEST FOR                              │
├──────────────────────┼───────────────────────────────────────────┤
│  Fixed-size (500 ch) │  General-purpose; simple to implement     │
│  Sentence boundary   │  Prose documents; preserves meaning       │
│  Heading-based       │  Markdown / RST; respects document        │
│                      │  structure                                │
│  Recursive splitter  │  Code; splits on class → func → line     │
└──────────────────────┴───────────────────────────────────────────┘
```

A chunk size of **400–600 characters** works well with the 4 000-character
context budget and a `top_k` of 5.

---

## 🔒 Security Considerations

- Knowledge bases are **shared across all authenticated users** — they are
  organisation-wide resources, not per-user.  Do not store secrets or PII
  in chunk content.
- The `Authorization: Bearer <GitHub PAT>` gate already applies to all
  `/api/knowledge-bases/*` endpoints.
- Chunk content is stored in plaintext in MongoDB.  If at-rest encryption is
  required, enable MongoDB's native encryption-at-rest feature or use a
  managed Atlas deployment with encryption enabled.

---

## 📡 Monitoring

Knowledge retrieval happens inside the Celery worker, so it appears in the
existing observability pipeline.  Look for the `knowledge_retrieved` log event
in the workflow's `logs[]` array (emitted when `retrieve()` returns a non-empty
context block).

---

<p align="center">⬛⬜⬛ <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⬛⬜⬛</p>
