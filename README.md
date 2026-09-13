# TrialScribe

### ICH M11 Clinical Trial Protocol & Report Generation from Trial Data

<p align="center">
  <img src="docs/assets/homepage.png" alt="TrialScribe landing page" width="900">
</p>

TrialScribe is a production-grade, multi-tenant SaaS platform that helps clinical research
teams draft **ICH M11–compliant clinical trial protocol sections** directly from trial data,
uploaded source documents, and external literature. Every AI-drafted claim is grounded in a
traceable citation — an uploaded document passage, a PubMed result, or a vetted web source —
rather than an unverifiable model assertion, and finished protocols export straight to a
Word (DOCX) deliverable.

## Highlights

- **Multi-tenant, event-driven microservices architecture** — a React/TypeScript authoring
  workspace behind a FastAPI API gateway, routing to five independently deployable backend
  services (authentication, organizations, AI conversations, document/evidence retrieval, and
  asynchronous job processing) connected through an Apache Kafka event backbone.
- **Retrieval-Augmented Generation (RAG) pipeline** — document ingestion, semantic chunking,
  embedding generation, and hybrid vector/relational retrieval (ChromaDB + PostgreSQL with
  pgvector) ground every generated protocol section in traceable source passages, PubMed
  literature, and allow-listed web evidence.
- **Enterprise-grade security posture** — Ed25519-signed JWT authentication, strict per-tenant
  data isolation, per-IP rate limiting, and upload validation, verified by automated
  authorization-bypass and tenant-leakage test coverage.
- **Production-ready operations** — Prometheus/Grafana observability across every service and
  a Docker Compose release profile load-validated at 500 concurrent users and 10,000 daily
  background-job equivalents, with one-click DOCX protocol export.

## System architecture

<p align="center">
  <img src="docs/assets/architecture-diagram.png" alt="TrialScribe system architecture diagram" width="900">
</p>

Request flow: the authoring workspace calls the API gateway, which authenticates and routes
to the backend service mesh; services coordinate long-running work over the Kafka event
backbone, persist tenant-scoped state in PostgreSQL/pgvector and ChromaDB, and reach external
LLM (DeepSeek, OpenAI) and research (PubMed, allow-listed web) providers only from the worker
boundary.

## Tech stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI, async SQLAlchemy, Alembic |
| Data & retrieval | PostgreSQL, pgvector, ChromaDB, Redis |
| Messaging | Apache Kafka (event-driven service backbone) |
| AI / RAG | Retrieval-Augmented Generation, OpenAI (embeddings), DeepSeek (chat & reasoning) |
| Infrastructure | Docker, Docker Compose, Prometheus, Grafana, k6 |

## Documentation

- [INFO.md](INFO.md) — local setup, environment configuration, and every command to run,
  test, and release the platform.
- [docs/architecture.md](docs/architecture.md) — full system design and roadmap.
- [docs/operations.md](docs/operations.md) — operational runbook for the Compose release profile.
- [docs/api-gateway.md](docs/api-gateway.md), [docs/auth-service.md](docs/auth-service.md),
  [docs/organization-rbac.md](docs/organization-rbac.md),
  [docs/conversation-workspaces.md](docs/conversation-workspaces.md) — service-level deep dives.
