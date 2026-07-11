# trialscribe-streamlit

Interim Streamlit UI for TrialScribe. Drives the `trialscribe-ai` agent pipeline directly for
local demos and manual testing, without going through the FastAPI session API.

**Status:** active (interim — will be replaced by [frontend/web](../web))

This is a standalone uv project (its own `pyproject.toml` and `uv.lock`) — it is **not** a
member of the `backend/` uv workspace. It depends on `trialscribe-ai` via an editable path
dependency pointing at `../../backend/services/ai-engine`.

## Run locally

```
cd frontend/streamlit-ui
uv sync
uv run streamlit run app.py
```

Or from the repo root: `./scripts.sh ui`.
