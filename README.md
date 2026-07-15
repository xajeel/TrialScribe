# TrialScribe

**TrialScribe** is an AI-powered clinical research assistant that researches and drafts
clinical trial protocol documents in the **ICH M11 format**. Its LangGraph pipeline gathers
evidence and composes structured, citation-backed protocol sections.

The repository is a service-oriented monorepo. Gateway, authentication, user, AI, worker,
and React boundaries can be run and verified independently before later features add their
domain behavior.

See [docs/architecture.md](docs/architecture.md) for the full system design and roadmap.

## Quickstart

Install `uv`, Node.js 24.18.0, and npm 11.16.0, then run:

```bash
./scripts.sh env
./scripts.sh install
./scripts.sh lint
./scripts.sh test
./scripts.sh smoke
```

Fill the provider placeholders in `.env` before using AI generation. Health and smoke checks
do not require real provider credentials.

## Application boundaries

| Boundary | Root command | Default port | Health |
|----------|--------------|--------------|--------|
| API gateway | `./scripts.sh run gateway` | 8000 | `/health/live`, `/health/ready` |
| Authentication | `./scripts.sh run auth` | 8001 | `/health/live`, `/health/ready` |
| User | `./scripts.sh run user` | 8002 | `/health/live`, `/health/ready` |
| AI engine | `./scripts.sh run ai` | 8003 | `/health/live`, `/health/ready` |
| Worker | `./scripts.sh run worker` | 8004 | `/health/live`, `/health/ready` |
| React web | `./scripts.sh run web` | 5173 | Browser root |

Override ports with `GATEWAY_PORT`, `AUTH_PORT`, `USER_PORT`, `AI_PORT`, `WORKER_PORT`, or
`WEB_PORT`. The web smoke preview uses `WEB_SMOKE_PORT` and defaults to 4173.

## Root commands

| Purpose | Command |
|---------|---------|
| Install frozen dependencies | `./scripts.sh install` |
| Create `.env` if missing | `./scripts.sh env` |
| Run a boundary | `./scripts.sh run <gateway\|auth\|user\|ai\|worker\|web>` |
| Lint Python and TypeScript | `./scripts.sh lint` |
| Run all service tests | `./scripts.sh test` |
| Smoke-test all boundaries | `./scripts.sh smoke` |
| Show command help | `./scripts.sh help` |

The existing `sync`, `api`, `ui`, and `up` commands remain compatibility aliases. `api` now
uses the AI boundary's standard port 8003; `ui` continues to run the interim Streamlit app,
and `up` continues to use the existing Docker Compose stack.

## Repository layout

- `backend/` — uv workspace containing gateway, auth, user, AI, and worker packages.
- `frontend/web/` — supported React application shell.
- `frontend/streamlit-ui/` — interim standalone Streamlit UI.
