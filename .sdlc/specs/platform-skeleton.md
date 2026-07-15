# platform-skeleton
Status: done
Goal: Establish six independently runnable TrialScribe application boundaries with one root workflow and verifiable health behavior.
Done when:
- A clean checkout completes the documented install, lint, and baseline test commands successfully.
- Automated smoke checks start gateway, auth, user, AI, worker, and React boundaries and receive healthy responses.
- Every backend boundary exposes separate liveness and readiness responses with the same data shape.

## What & why — plain English
TrialScribe needs stable homes for each part of the future product before those parts gain real behavior. This feature turns the planned gateway, authentication, user, worker, and React folders into small applications while keeping the existing AI engine intact. A developer will use the same root command to install, run, check, or test any boundary. Automated smoke checks will start each application and prove it can answer, so later features can add databases, queues, security, and product screens without reorganizing the repository. This feature adds no authentication, persistence, messaging, gateway routing, or production authoring behavior.

## Decisions
- **Backend application boundaries** — An application boundary is code that can start and be released without importing another service's internals.
  Chose: separate uv workspace packages using FastAPI (a Python library for web services) for gateway, auth, user, AI, and worker. Why: this matches the existing AI service and keeps later releases independent.
  Rejected: README-only placeholders or one combined backend — neither proves that the boundaries actually run.
- **Health contract** — Liveness says a process is running; readiness says it is prepared to accept work.
  Chose: `GET /health/live` and `GET /health/ready`, each returning status, service name, and version; dependency checks can be added by later features. Why: separate addresses keep the two meanings clear and testable.
  Rejected: one `/health` address — it cannot later distinguish a stuck process from an unavailable dependency.
- **Worker shell** — The worker will eventually consume background jobs rather than serve product requests.
  Chose: give it a minimal FastAPI companion with health addresses and no job routes. Why: the roadmap requires every backend boundary to start and report health before queue behavior exists.
  Rejected: a sleeping command-line process — smoke tests could not receive a readiness response from it.
- **React shell** — A SPA (a web page that updates without full-page reloads) is the future supported browser application.
  Chose: Node.js 24.18.0 LTS with npm 11.16.0, React 19.2.7, TypeScript 7.0.2, Vite 8.1.4, and Vitest 4.1.10. Why: Node's LTS line is recommended for production, and these are stable current releases.
  Rejected: extending Streamlit or adding a JavaScript monorepo manager — Streamlit is out of v1, and one JavaScript app does not justify another tool.
- **Release isolation** — Each service owns its package, health model, application object, and tests.
  Chose: repeat the tiny health contract in each service. Why: changing or releasing one service will not require a shared runtime package.
  Rejected: a common Python health library — it creates cross-service release coupling before shared behavior is needed.
- **Root workflow** — `scripts.sh` remains the single human entry point, with a small Python process-level smoke runner behind it.
  Chose: extend the tools already present. Why: developers get consistent commands without learning or installing a task orchestrator.
  Rejected: Make, Turborepo, or Nx — they add a second command system without solving a current need.

## Touches
- Edits: `backend/pyproject.toml`, `backend/uv.lock`, `.sdlc/CRAFT.md`, `.sdlc/PROJECT.md`, `.env_example`, `scripts.sh`, and `README.md` standardize the workspace and root workflow; planned-service READMEs become shell documentation; `backend/services/ai-engine/trialscribe_ai/api/app.py`, its smoke test, and README gain the shared health contract; `frontend/web/README.md` becomes runnable-shell documentation.
- Adds: four backend service manifests and Python packages, service-local health tests, the React/Vite application and lockfile, `.nvmrc`, and `scripts/smoke_platform.py`.
- Mirrors: `backend/services/ai-engine/pyproject.toml` for Python package metadata; `backend/services/ai-engine/trialscribe_ai/api/app.py` and `backend/services/ai-engine/tests/test_smoke.py` for FastAPI and pytest style; `scripts.sh` for root command behavior.
- Risk: existing AI session routes, the backend uv lock, root quickstart commands, AI port expectations, legacy `api`/`ui`/`up` commands, and the interim Streamlit workflow must continue working.

## Tasks

### [x] T1 — Register backend service packages
Files: EDIT backend/pyproject.toml, EDIT backend/uv.lock, EDIT .sdlc/CRAFT.md, CREATE backend/services/api-gateway/pyproject.toml, CREATE backend/services/api-gateway/trialscribe_gateway/__init__.py, CREATE backend/services/auth-service/pyproject.toml, CREATE backend/services/auth-service/trialscribe_auth/__init__.py, CREATE backend/services/user-service/pyproject.toml, CREATE backend/services/user-service/trialscribe_user/__init__.py, CREATE backend/services/worker-service/pyproject.toml, CREATE backend/services/worker-service/trialscribe_worker/__init__.py
Pattern: backend/services/ai-engine/pyproject.toml
Do:
- Name the distributions `trialscribe-gateway`, `trialscribe-auth`, `trialscribe-user`, and `trialscribe-worker`; map them to the matching `trialscribe_*` package directories.
- Require Python `>=3.12` and `fastapi[standard]>=0.115.14,<0.116` in every new service; use the existing Hatchling build backend.
- Add all five backend services as explicit uv workspace members; do not make one service depend on another.
- Add the new service/package/test paths and the no-cross-service-import rule to CRAFT.md.
- Regenerate `backend/uv.lock` with uv; never edit lock entries by hand.
Verify: `cd backend && uv lock --check && uv sync --frozen --all-packages` → all five workspace packages resolve and install.

### [x] T2 — Add gateway and authentication shells
Files: EDIT backend/pyproject.toml, CREATE backend/services/api-gateway/README.md, CREATE backend/services/api-gateway/trialscribe_gateway/api/__init__.py, CREATE backend/services/api-gateway/trialscribe_gateway/api/app.py, CREATE backend/services/api-gateway/trialscribe_gateway/models/__init__.py, CREATE backend/services/api-gateway/trialscribe_gateway/models/health.py, CREATE backend/services/api-gateway/tests/test_health.py, EDIT backend/services/auth-service/README.md, CREATE backend/services/auth-service/trialscribe_auth/api/__init__.py, CREATE backend/services/auth-service/trialscribe_auth/api/app.py, CREATE backend/services/auth-service/trialscribe_auth/models/__init__.py, CREATE backend/services/auth-service/trialscribe_auth/models/health.py, CREATE backend/services/auth-service/tests/test_health.py
Pattern: backend/services/ai-engine/trialscribe_ai/api/app.py, backend/services/ai-engine/tests/test_smoke.py
Do:
- Define `HealthResponse(status: Literal["ok", "ready"], service: str, version: str)` in each service's health model.
- Expose typed `app: FastAPI` objects named `TrialScribe Gateway` and `TrialScribe Auth`, both version `0.1.0`.
- Add async `GET /health/live` and `GET /health/ready` handlers with exact service values `api-gateway` and `auth-service`.
- Return `ok` from liveness and `ready` from readiness; add no proxy, identity, token, database, or cross-service behavior.
- Test both addresses through `TestClient`, including status 200 and exact response bodies.
- Configure pytest to use importlib collection mode so identical service-local test module names remain isolated.
- Mark each README as a runnable shell and document its direct uv/uvicorn command and deferred responsibilities.
Verify: `cd backend && uv run pytest services/api-gateway/tests services/auth-service/tests -q` → four health checks pass.

### [x] T3 — Add user and worker shells
Files: EDIT backend/services/user-service/README.md, CREATE backend/services/user-service/trialscribe_user/api/__init__.py, CREATE backend/services/user-service/trialscribe_user/api/app.py, CREATE backend/services/user-service/trialscribe_user/models/__init__.py, CREATE backend/services/user-service/trialscribe_user/models/health.py, CREATE backend/services/user-service/tests/test_health.py, EDIT backend/services/worker-service/README.md, CREATE backend/services/worker-service/trialscribe_worker/api/__init__.py, CREATE backend/services/worker-service/trialscribe_worker/api/app.py, CREATE backend/services/worker-service/trialscribe_worker/models/__init__.py, CREATE backend/services/worker-service/trialscribe_worker/models/health.py, CREATE backend/services/worker-service/tests/test_health.py
Pattern: backend/services/api-gateway/trialscribe_gateway/api/app.py, backend/services/api-gateway/tests/test_health.py
Do:
- Mirror the gateway health model and route contract without importing gateway code.
- Expose typed `app: FastAPI` objects named `TrialScribe User` and `TrialScribe Worker`, both version `0.1.0`.
- Use exact service values `user-service` and `worker-service` in both health responses.
- Add no user records, organizations, storage, queues, job execution, polling, or cross-service behavior.
- Test liveness and readiness through `TestClient`, including status 200 and exact response bodies.
- Mark each README as a runnable shell and keep future domain responsibilities explicitly deferred.
Verify: `cd backend && uv run pytest services/user-service/tests services/worker-service/tests -q` → four health checks pass.

### [x] T4 — Give the AI engine the shared health contract
Files: CREATE backend/services/ai-engine/trialscribe_ai/models/health.py, EDIT backend/services/ai-engine/trialscribe_ai/api/app.py, EDIT backend/services/ai-engine/tests/test_smoke.py, EDIT backend/services/ai-engine/README.md
Pattern: backend/services/api-gateway/trialscribe_gateway/models/health.py, backend/services/api-gateway/trialscribe_gateway/api/app.py
Do:
- Add the same `HealthResponse` shape locally under `trialscribe_ai.models`.
- Add async `GET /health/live` and `GET /health/ready` handlers returning service `ai-engine`, version `2.0.0`, and statuses `ok` and `ready`.
- Keep health handlers free of model calls, evidence retrieval, file access, and outbound network requests.
- Preserve every existing session, upload, report, lifespan, and CORS behavior unchanged.
- Extend smoke tests to call both health addresses and retain the existing graph and trial-processor regressions.
- Document both health addresses in the AI service README.
Verify: `cd backend && uv run pytest services/ai-engine/tests/test_smoke.py -q` → existing smoke coverage and two health checks pass.

### [x] T5 — Create the React application shell
Files: CREATE .nvmrc, EDIT .sdlc/CRAFT.md, EDIT frontend/web/README.md, CREATE frontend/web/package.json, CREATE frontend/web/package-lock.json, CREATE frontend/web/index.html, CREATE frontend/web/tsconfig.json, CREATE frontend/web/vite.config.ts, CREATE frontend/web/src/main.tsx, CREATE frontend/web/src/App.tsx, CREATE frontend/web/src/styles.css, CREATE frontend/web/src/App.test.tsx
Pattern: frontend/web/README.md
Do:
- Pin Node `24.18.0` in `.nvmrc` and `engines`, and set `packageManager` to `npm@11.16.0`.
- Pin runtime packages `react@19.2.7` and `react-dom@19.2.7` exactly.
- Pin dev packages `@types/react@19.2.17`, `@types/react-dom@19.2.3`, `@vitejs/plugin-react@6.0.3`, `typescript@7.0.2`, `vite@8.1.4`, and `vitest@4.1.10` exactly; record them in CRAFT.md.
- Define `dev`, `build`, `preview`, `lint` (`tsc --noEmit`), and `test` (`vitest run`) scripts and strict TypeScript settings.
- Render an accessible shell whose visible heading is `TrialScribe` and whose copy says the platform shell is ready; add no routing, API client, auth, or authoring UI.
- Test the server-rendered `App` output for the heading and shell-ready copy; generate `package-lock.json` with npm, never by hand.
- Mark the README as a runnable shell and document install, dev, lint, test, and build commands.
Verify: `cd frontend/web && npm ci && npm run lint && npm test && npm run build` → type-check, unit test, and production build pass.

### [x] T6 — Standardize root commands and configuration
Files: EDIT scripts.sh, EDIT .env_example, EDIT .sdlc/PROJECT.md, EDIT README.md
Pattern: scripts.sh
Do:
- Support `install`, `env`, `run <gateway|auth|user|ai|worker|web>`, `lint`, `test`, `smoke`, and `help` from the repository root.
- Make `install` run frozen backend workspace sync plus `npm ci`; make `env` copy `.env_example` only when `.env` does not exist.
- Map backend runs to their own uv package and uvicorn import, and map web to Vite; use ports 8000 gateway, 8001 auth, 8002 user, 8003 AI, 8004 worker, and 5173 web with environment overrides.
- Make `lint` run Ruff plus the web type-check, and `test` run every backend service test plus the web test suite.
- Preserve the existing `sync`, `api`, `ui`, and `up` commands as documented compatibility aliases; do not change Docker Compose in this feature.
- Add all port keys to `.env_example` with non-secret defaults and update PROJECT.md and README.md with the exact root workflow and boundary table.
Verify: `bash -n scripts.sh && ./scripts.sh help` → exits 0 and lists every supported command and service selector.

### [x] T7 — Prove every boundary starts
Files: CREATE scripts/smoke_platform.py
Pattern: scripts.sh
Do:
- Implement a Python 3.12 smoke runner using only the standard library, explicit argument lists, and `subprocess.Popen` without `shell=True`.
- Start gateway, auth, user, AI, and worker one at a time on their configured ports; give the AI child non-secret dummy provider values only when its environment lacks them.
- Poll each backend for at most 30 seconds; require exact 200 liveness and readiness bodies matching its service and version.
- Build the React shell once, start Vite preview on port 4173 (override `WEB_SMOKE_PORT`), and require its root HTML to contain `TrialScribe`.
- Capture bounded child output for failure messages without printing environment values, file contents, or secrets.
- Always terminate, then kill on timeout, every child process; print one success line per boundary and exit nonzero on the first failure.
Verify: `./scripts.sh smoke` → reports healthy gateway, auth, user, AI, worker, and web boundaries, then leaves no child processes running.

## Acceptance checks
- [ ] `./scripts.sh install` → frozen Python and npm dependencies install from a clean checkout.
- [ ] `./scripts.sh lint` → Ruff and strict TypeScript checks pass with no errors.
- [ ] `./scripts.sh test` → all backend health/regression tests and the React shell test pass.
- [ ] `./scripts.sh smoke` → all six application boundaries start, answer their health check, and stop cleanly.

## QA log
<!-- appended by /qa -->

### QA 2026-07-15 — PASS
Task verifies: 7/7 · Acceptance: 4/4 · Suite: 14 passed, 0 failed · Regressions: 0
Unlisted changes: none · Craft scan: clean
Failures: none
Notes: Host Node 20.20.2/npm 10.8.2 emitted the expected engine warning for the pinned Node 24.18.0/npm 11.16.0 project; all checks passed. Existing LangGraph pending-deprecation warning remains.
Try it:
1. Run `GATEWAY_PORT=18000 ./scripts.sh run gateway` from the repository root.
2. Open `http://localhost:18000/health/ready`.
3. Expect `{"status":"ready","service":"api-gateway","version":"0.1.0"}`, then press Ctrl-C.
