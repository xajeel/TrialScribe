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

### v1 production

v1 production is the Docker Compose **release** profile (`./scripts.sh release up`): one
host runs the data stores, a migrate gate, the API gateway, auth, user, AI, worker, jobs
reader, and the nginx-hosted React website. Host `uvicorn` processes are a local development
path. Operator steps (backup, restore, upgrade, rollback, capacity) live in
[operations.md](operations.md).

### Repository tooling structure

`backend/` is a self-contained uv workspace: `backend/pyproject.toml` is the workspace root
for every Python service. `frontend/web` is a standalone npm project, so the two toolchains
never share a workspace root.

## Roadmap

The monorepo layout anticipates the following services as independent, addable units:

- **`auth-service`** — JWT-based authentication and RBAC authorization, so protocol generation
  can be gated per user/organization instead of being open by session ID alone.
- **`user-service`** — persistent users, accounts, and organizations backed by PostgreSQL,
  replacing the in-memory `ACTIVE_SESSIONS` dict with durable session/user records.
- **`worker-service`** — background job execution (e.g. Celery/Redis or ARQ) so long-running
  protocol generation runs outside the request/response cycle, with status polling instead of
  a blocking `generate-report` call.
- **`frontend/web`** — the React + TypeScript application, talking to backend services
  through the API gateway.
- **API gateway** — once multiple backend services exist, a gateway/reverse proxy in front of
  them for unified routing, auth enforcement, and rate limiting.

Each planned service currently has a `README.md` describing its intended responsibility and
API surface, with `Status: planned` — no stub application code exists until it's built.
