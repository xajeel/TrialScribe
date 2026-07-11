# frontend/web

**Status:** planned

The React + TypeScript SPA that will replace `frontend/streamlit-ui` as TrialScribe's primary
frontend once the backend exposes stable session, auth, and job-status APIs.

## Planned responsibility

- Trial JSON + supporting document upload flow.
- Research query submission and live job-status/progress display (once `worker-service` exists).
- Rendering generated protocol sections with citations, and basic report history per user.
- Auth flows (login/logout) against `auth-service`.

## Planned tech stack

React + TypeScript, Vite, a data-fetching layer (e.g. TanStack Query) against the FastAPI
services, deployed as a static build served separately from the backend.

## Planned API surface consumed

- `ai-engine`: `/sessions`, `/sessions/{id}/upload-json`, `/sessions/{id}/upload-documents`,
  `/sessions/{id}/generate-report` (or the async `worker-service` job endpoints once available).
- `auth-service`: `/auth/login`, `/auth/refresh`, `/auth/me`.
- `user-service`: `/users/{id}/sessions` for report history.
