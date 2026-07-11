# backend

Backend services for TrialScribe, under `services/`. Each service is an independently
runnable/deployable unit with its own `pyproject.toml` (Python services) and `README.md`.

`backend/` is its own self-contained uv workspace — `backend/pyproject.toml` is the workspace
root and `backend/uv.lock` is the shared lockfile for every Python service listed as a member
below. Run `uv sync --all-packages` from within `backend/` (or `./scripts.sh sync` from the
repo root) to install all of them into one environment.

| Service | Status |
|---------|--------|
| [ai-engine](services/ai-engine) | active |
| [auth-service](services/auth-service) | planned |
| [user-service](services/user-service) | planned |
| [worker-service](services/worker-service) | planned |

`fixtures/` holds sample trial-data files (JSON + a PDF) used for local development and manual
testing — not consumed by any code path, just handy inputs to exercise the upload flow with.
