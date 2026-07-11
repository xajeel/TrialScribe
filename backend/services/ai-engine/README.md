# trialscribe-ai

The core AI engine for TrialScribe: a LangGraph multi-agent pipeline (planner → researcher →
writer) that researches and drafts clinical trial protocol documents in the ICH M11 format,
exposed as a FastAPI service.

**Status:** active

## Run locally

From `backend/` (`load_dotenv()` searches upward from cwd, so the repo-root `.env` still
resolves; the FAISS runtime indexes are created relative to wherever you run from):

```
cd backend
uv sync --all-packages
uv run --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --reload
```

Or from the repo root: `./scripts.sh api`.

API docs: `http://localhost:8000/docs`

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sessions` | Create a session |
| DELETE | `/sessions/{session_id}` | Delete a session |
| POST | `/sessions/{session_id}/upload-json` | Upload trial design JSON |
| POST | `/sessions/{session_id}/upload-documents` | Upload supporting PDFs |
| POST | `/sessions/{session_id}/generate-report` | Run the agent pipeline and generate protocol text |

## Tests

```
cd backend
uv run --package trialscribe-ai pytest services/ai-engine/tests/
```

Or from the repo root: `./scripts.sh test`.
