# user-service

**Status:** planned

Owns durable user, account, and organization data for TrialScribe. Replaces the AI engine's
current in-memory `ACTIVE_SESSIONS` model with persistent records so sessions, uploaded
documents, and generated reports survive restarts and are attributable to a real user.

## Planned responsibility

- User and organization CRUD.
- Persistent trial-generation session/report history (currently in-memory in `ai-engine`).
- Ownership and access checks for uploaded documents and generated protocols.

## Planned tech stack

FastAPI, SQLAlchemy + Alembic migrations, PostgreSQL.

## Planned API surface

- `POST /users` — create a user (typically called by `auth-service` on signup).
- `GET /users/{user_id}` — fetch a user's profile.
- `GET /organizations/{org_id}/members` — list an organization's users.
- `POST /organizations` — create an organization.
- `GET /users/{user_id}/sessions` — list a user's past trial-generation sessions/reports.
