# trialscribe-ai

The AI engine HTTP boundary for TrialScribe: it accepts work onto Kafka and reads
durable conversation, document, and M11 section state. Model, embedding, and vector
calls run in the worker behind the provider gateway.

**Status:** active

## Run locally

From `backend/`:

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

Work that talks to a model is requested as a job (`provider_probe` proves the door).
PostgreSQL conversation messages are the source of truth for product memory.
See `docs/conversation-workspaces.md` for the flow, permissions, pagination, and error contracts.

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
