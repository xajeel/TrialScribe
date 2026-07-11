# TrialScribe

**TrialScribe** is an AI-powered clinical research assistant that researches and drafts clinical trial protocol documents in the **ICH M11 format**. A multi-agent pipeline (planner → researcher → writer) built with LangGraph gathers evidence from PubMed, ClinicalTrials.gov-style trial data, and domain-restricted web search (Tavily), then composes structured, citation-backed protocol sections.

The repository is organized as a service-oriented monorepo so new capabilities — authentication, persistent storage, background processing, a React frontend — can be added as independent services rather than bolted onto a single script.

## Architecture

```
                         ┌───────────────────────┐
   ┌──────────────┐      │   backend/services    │
   │  frontend/    │      │                       │
   │  streamlit-ui │─────▶│   ai-engine (FastAPI) │
   │ (interim UI)  │      │                       │
   └──────────────┘      │  ┌─────────────────┐   │
                          │  │ planner_node    │   │
   ┌──────────────┐      │  │      ↓          │   │
   │  frontend/    │      │  │ research_node   │──▶│───▶ PubMed (NCBI e-utils)
   │  web (planned)│─────▶│  │      ↓          │   │───▶ Tavily web search
   │  React SPA    │      │  │ writer_node     │   │      (allow-listed domains)
   └──────────────┘      │  └─────────────────┘   │
                          │         ↓               │
                          │  FAISS evidence store   │
                          └───────────────────────┘

        (planned)  auth-service · user-service · worker-service
```

See [docs/architecture.md](docs/architecture.md) for the full system design and roadmap.

## Services

| Service | Path | Status |
|---------|------|--------|
| AI engine | [backend/services/ai-engine](backend/services/ai-engine) | active |
| Streamlit UI | [frontend/streamlit-ui](frontend/streamlit-ui) | active (interim) |
| Auth service | [backend/services/auth-service](backend/services/auth-service) | planned |
| User service | [backend/services/user-service](backend/services/user-service) | planned |
| Worker service | [backend/services/worker-service](backend/services/worker-service) | planned |
| React web frontend | [frontend/web](frontend/web) | planned |

## Quickstart

```
pip install uv
uv sync --all-packages
```

| Purpose   | Command (from repo root) |
|-----------|---------------------------|
| API       | `uv run --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --reload` |
| Streamlit | `uv run --package trialscribe-streamlit streamlit run frontend/streamlit-ui/app.py` |
| Both via Docker | `docker compose up` |
| Smoke tests | `uv run --package trialscribe-ai pytest backend/services/ai-engine/tests/` |

Or simply `make api` / `make ui` / `make test` / `make up` (see [Makefile](Makefile)).

Copy `.env_example` to `.env` and fill in `OPENAI_API_KEY`, `TAVILY_API_KEY`, and `NCBI_API_KEY` before running.
