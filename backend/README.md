# backend

Backend services for TrialScribe, under `services/`. Each service is an independently
runnable/deployable unit with its own `pyproject.toml` (Python services) and `README.md`.

| Service | Status |
|---------|--------|
| [ai-engine](services/ai-engine) | active |
| [auth-service](services/auth-service) | planned |
| [user-service](services/user-service) | planned |
| [worker-service](services/worker-service) | planned |

Python services are managed as members of the root `uv` workspace — run `uv sync` from the
repo root to install all of them into one environment.
