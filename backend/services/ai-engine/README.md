# trialscribe-ai

The core AI engine for TrialScribe: a LangGraph multi-agent pipeline (planner → researcher →
writer) that researches and drafts clinical trial protocol documents in the ICH M11 format,
exposed as a FastAPI service.

**Status:** active

## Run locally

From the repo root (so `.env` and the FAISS runtime indexes resolve correctly):

```
uv sync --all-packages
uv run --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --reload
```

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
uv run --package trialscribe-ai pytest backend/services/ai-engine/tests/
```
