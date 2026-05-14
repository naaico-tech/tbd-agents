# Scaling

TBD Agents is designed for horizontal scaling from day one. All components are stateless (except the databases), so you can add capacity by running more instances.

---

## Scaling Strategy

```mermaid
graph TB
    subgraph Load Balancer
        LB[Reverse Proxy / Ingress]
    end

    subgraph API Instances
        API1[FastAPI #1]
        API2[FastAPI #2]
        API3[FastAPI #N]
    end

    subgraph Worker Pool
        W1[Worker #1<br/>concurrency=4]
        W2[Worker #2<br/>concurrency=4]
        W3[Worker #N<br/>concurrency=4]
    end

    subgraph Infrastructure
        Redis[(Redis Cluster)]
        Store[(MongoDB replica set or PostgreSQL HA)]
    end

    LB --> API1 & API2 & API3
    API1 & API2 & API3 --> Redis
    API1 & API2 & API3 --> Store
    Redis --> W1 & W2 & W3
    W1 & W2 & W3 --> Store
    W1 & W2 & W3 --> Redis
```

---

## Horizontal Worker Scaling

Workers are stateless — they load persistent state from MongoDB or PostgreSQL and communicate via Redis. Add more containers to handle more concurrent agent runs.

```bash
# Docker Compose — run 5 worker containers
docker compose up --build --scale worker=5

# Each worker runs --concurrency=4
# Total = 20 concurrent agent executions
```

---

## Horizontal API Scaling

The FastAPI `app` service is also stateless. Run multiple instances behind a load balancer:

```bash
docker compose up --build --scale app=3
```

SSE connections are per-client, and each API instance independently subscribes to Redis pub/sub for the relevant workflow channel.

---

## Infrastructure Scaling

| Component | Strategy |
|---|---|
| **Redis** | Redis Sentinel or Redis Cluster for high availability |
| **Document store** | MongoDB replica sets/Atlas or PostgreSQL HA/managed Postgres |
| **Vector store** | Qdrant cluster/cloud or PostgreSQL pgvector on the PostgreSQL backend |
| **Workers** | Increase `--concurrency` per container or add containers |
| **API** | Multiple instances behind a reverse proxy |

---

## Kubernetes / Helm

TBD Agents includes Helm charts for Kubernetes deployment with:

- **API HPA** — Horizontal Pod Autoscaler for the FastAPI service
- **KEDA ScaledObject** — Autoscale workers based on Redis queue length
- **PVC** — Persistent volume claims for data
- **Ingress** — Configurable ingress for external access

```mermaid
graph LR
    Ingress[Ingress Controller] --> APISvc[API Service]
    APISvc --> APIPods[API Pods<br/>HPA: 2-10]
    KEDA[KEDA] -->|Scale on queue depth| WorkerPods[Worker Pods<br/>ScaledObject: 1-20]
    APIPods --> Redis[(Redis)]
    APIPods --> Mongo[(MongoDB)]
    WorkerPods --> Redis
    WorkerPods --> Mongo
```

---

## Capacity Planning

| Metric | Guidance |
|---|---|
| **Concurrent agents** | 1 agent ≈ 1 Celery task slot. `workers × concurrency` = max concurrent |
| **Memory per worker** | ~256MB base + SDK overhead per concurrent task |
| **Redis memory** | Minimal for pub/sub; grows with in-flight task count |
| **MongoDB storage** | ~10KB per workflow message; grows with conversation history |
| **SSE connections** | 1 per active client; lightweight on API side |
