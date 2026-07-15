# Code Craft — TrialScribe
Source: derived from codebase · 2026-07-15

## Stack — pinned
- Python 3.12.3 · uv 0.10.7; backend workspace and Streamlit UI keep separate lockfiles
- FastAPI 0.115.14 · LangGraph 0.4.10 · LangChain 0.3.30 · OpenAI 1.109.1
- Pydantic 2.13.4 — use `model_validate()` and `model_dump()`; legacy `parse_obj()` and `dict()` forbidden
- Streamlit 1.59.1
- Node.js 24.18.0 LTS · npm 11.16.0 · React/React DOM 19.2.7 · TypeScript 7.0.2 · Vite 8.1.4 · Vitest 4.1.10 · `@vitejs/plugin-react` 6.0.3 · React types 19.2.17/19.2.3
- pytest 9.1.1 · Ruff 0.15.21
> New dependency → latest stable, exact version recorded here in the same task.

## Structure
- `backend/services/api-gateway/trialscribe_gateway/` → FastAPI gateway boundary; tests live in `backend/services/api-gateway/tests/test_*.py`
- `backend/services/auth-service/trialscribe_auth/` → FastAPI authentication boundary; tests live in `backend/services/auth-service/tests/test_*.py`
- `backend/services/user-service/trialscribe_user/` → FastAPI user boundary; tests live in `backend/services/user-service/tests/test_*.py`
- `backend/services/ai-engine/trialscribe_ai/api/` → FastAPI application and session boundaries
- `backend/services/ai-engine/trialscribe_ai/agents/` → LangGraph nodes and graph assembly
- `backend/services/ai-engine/trialscribe_ai/models/` → Pydantic domain and state models
- `backend/services/ai-engine/trialscribe_ai/retrieval/` → external evidence retrieval and trial-data processing
- `backend/services/ai-engine/trialscribe_ai/storage/` → evidence persistence and vector-store access
- `backend/services/ai-engine/trialscribe_ai/services/` → application orchestration
- `backend/services/ai-engine/trialscribe_ai/prompts/` → prompt templates only
- `backend/services/ai-engine/trialscribe_ai/config/` → runtime settings and allow-lists
- `backend/services/ai-engine/tests/test_*.py` → pytest tests
- `backend/services/worker-service/trialscribe_worker/` → FastAPI worker health boundary; tests live in `backend/services/worker-service/tests/test_*.py`
- `frontend/streamlit-ui/` → interim Streamlit UI; `frontend/web/` remains a separate planned frontend
- `frontend/web/src/` → React application shell and colocated `*.test.tsx` unit tests
- New files go in the directory matching their concern; never place application modules at repository root.

## Style
- Modules, functions, and variables use `snake_case`; classes use `PascalCase`.
- Use absolute `trialscribe_ai.*` imports across packages.
- FastAPI request and response bodies use Pydantic models at the route boundary.
- Async graph or I/O operations are awaited end-to-end; do not call async functions without `await`.
- Route handlers raise `HTTPException` with an appropriate 4xx status for invalid user input.
- Tests use `test_*.py` files and `test_*` functions with direct assertions.
- Ruff is the formatting and lint authority; imports and spacing currently diverge in legacy modules `(legacy)`.
- Add type annotations to every new or changed function; existing untyped functions are `(legacy)`.
- Do not duplicate graph assembly or business logic in UI modules; current Streamlit duplication is `(legacy)`.
- One concern per module; API routes, models, retrieval, storage, and graph construction remain separate.

## Config & secrets
- Runtime config is read from environment variables in `backend/services/ai-engine/trialscribe_ai/config/settings.py`.
- Every new key → `.env_example` with a placeholder in the same task.
- Never hardcode secrets, external service credentials, or deployment URLs in source.

## Security baseline
- Validate request bodies and uploaded file type/content at the FastAPI boundary before processing.
- Restrict external retrieval to configured allow-lists where supported.
- Never log or return API keys, uploaded document contents, or trial data unintentionally.
- Error responses never expose stack traces, queries, exception strings, or internals; current broad exception details are `(legacy)`.
- CORS must use explicit configured origins outside local development; wildcard CORS is `(legacy)`.
- No relational database or authentication layer exists yet; introduce their security rules with those features.

## Boundaries
- Services never import another service's application package; each boundary owns its runtime contracts and release lifecycle.
- Never hand-edit `backend/uv.lock` or `frontend/streamlit-ui/uv.lock`; regenerate them with uv.
- Never edit virtual environments, Ruff caches, generated artifacts, or planned-service placeholders as a side effect.
- Never commit `.env`, secrets, uploaded trial data, or build artifacts; `.env_example` contains placeholders only.
