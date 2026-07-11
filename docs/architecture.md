# TrialScribe — Architecture

## Current system

TrialScribe's core is a LangGraph state machine with three sequential nodes, orchestrated per
user session:

1. **Planner** (`trialscribe_ai/agents/planner.py`) — takes the user's query and a summary of
   the uploaded trial-design JSON, and produces a list of ICH M11 protocol sections to write.
2. **Researcher** (`trialscribe_ai/agents/researcher.py`) — for each section, generates search
   queries and pulls supporting evidence from two sources:
   - **PubMed** (`trialscribe_ai/retrieval/pubmed.py`) via the NCBI E-utilities API.
   - **Tavily web search** (`trialscribe_ai/retrieval/tavily.py`), restricted to an allow-list
     of trusted domains (`trialscribe_ai/config/allowed_websites.yml`).

   Retrieved evidence is chunked and embedded into a FAISS vector store
   (`trialscribe_ai/storage/evidence_db.py`), which also stores user-uploaded supporting PDFs
   and the trial-design JSON summary.
3. **Writer** (`trialscribe_ai/agents/writer.py`) — for each section, retrieves the most
   relevant chunks from the FAISS stores (`trialscribe_ai/retrieval/retriever.py`) and prompts
   an LLM to draft the section text, citing sources.

State (`AgentState` in `trialscribe_ai/models/schemas.py`) flows through the graph: query →
sections → written texts.

### Session model

The FastAPI service (`trialscribe_ai/api/app.py`, `trialscribe_ai/api/sessions.py`) keeps
per-session state in memory: an `EvidenceDatabase` instance, a compiled agent graph, uploaded
document paths, and the trial-design summary. Sessions expire after 2 hours of inactivity via
a background cleanup task. This in-memory model is intentionally simple for a single-instance
deployment — see the Roadmap below for how it evolves.

### Interim frontend

`frontend/streamlit-ui` is a thin Streamlit app that drives the same agent pipeline directly
(without going through the FastAPI session API) for local demos and manual testing.

## Roadmap

The monorepo layout anticipates the following services as independent, addable units:

- **`auth-service`** — JWT-based authentication and RBAC authorization, so protocol generation
  can be gated per user/organization instead of being open by session ID alone.
- **`user-service`** — persistent users, accounts, and organizations backed by PostgreSQL,
  replacing the in-memory `ACTIVE_SESSIONS` dict with durable session/user records.
- **`worker-service`** — background job execution (e.g. Celery/Redis or ARQ) so long-running
  protocol generation runs outside the request/response cycle, with status polling instead of
  a blocking `generate-report` call.
- **`frontend/web`** — a React + TypeScript SPA replacing the Streamlit UI as the primary
  frontend, talking to the AI engine (and eventually the other services) over HTTP.
- **API gateway** — once multiple backend services exist, a gateway/reverse proxy in front of
  them for unified routing, auth enforcement, and rate limiting.

Each planned service currently has a `README.md` describing its intended responsibility and
API surface, with `Status: planned` — no stub application code exists until it's built.
