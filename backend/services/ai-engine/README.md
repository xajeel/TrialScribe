# trialscribe-ai

The core AI engine for TrialScribe: a LangGraph multi-agent pipeline (planner → researcher →
writer) that researches and drafts clinical trial protocol documents in the ICH M11 format,
exposed as a FastAPI service.

**Status:** active

## Run locally

From `backend/` (the FAISS runtime indexes are created relative to wherever you run from):

```
cd backend
uv sync --all-packages
uv run --env-file ../.env --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --reload --port 8003
```

Or from the repo root: `./scripts.sh run ai`.

Internal API docs: `http://localhost:8003/docs`. Browser clients use the public gateway on
port `8000`, where conversation paths begin with `/v1/ai`.

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health/live` | Report process liveness |
| GET | `/health/ready` | Report readiness to accept work |
| POST/GET | `/conversations` | Create or page durable conversations |
| GET/PATCH/DELETE | `/conversations/{conversation_id}` | Open, rename, or archive a conversation |
| POST | `/conversations/{conversation_id}/restore` | Restore an archived conversation |
| PUT | `/conversations/{conversation_id}/collaborators` | Replace creator-managed access |
| POST/GET | `/conversations/{conversation_id}/messages` | Append or page durable message history |
| POST | `/sessions` | Create a session |
| DELETE | `/sessions/{session_id}` | Delete a session |
| POST | `/sessions/{session_id}/upload-json` | Upload trial design JSON |
| POST | `/sessions/{session_id}/upload-documents` | Upload supporting PDFs |
| POST | `/sessions/{session_id}/generate-report` | Run the agent pipeline and generate protocol text |

The `/sessions` routes are transitional process-local behavior. New features attach to durable
conversation IDs. PostgreSQL conversation messages are the source of truth for product memory;
Redis and future LangGraph checkpoints do not replace that visible history. See
`docs/conversation-workspaces.md` for the flow, permissions, pagination, and error contracts.

## Tests

```
cd backend
uv run --package trialscribe-ai pytest services/ai-engine/tests/
```

Or from the repo root: `./scripts.sh test`.

Run the isolated migration, restart, tenant-isolation, and membership-revocation lifecycle with:

```
./scripts.sh ai test
```
