# trialscribe-streamlit

Interim Streamlit UI for TrialScribe. Drives the `trialscribe-ai` agent pipeline directly for
local demos and manual testing, without going through the FastAPI session API.

**Status:** active (interim — will be replaced by [frontend/web](../web))

## Run locally

From the repo root:

```
uv sync --all-packages
uv run --package trialscribe-streamlit streamlit run frontend/streamlit-ui/app.py
```
