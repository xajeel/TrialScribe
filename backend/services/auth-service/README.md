# auth-service

**Status:** local account authentication

The service owns global email/password accounts, short-lived Ed25519 access tokens, rotated
and revocable refresh sessions, CSRF-protected refresh cookies, and Redis login throttling.
Organization invitations, memberships, and roles remain owned by the organization-RBAC
feature so one identity can join multiple organizations.

See [`docs/auth-service.md`](../../../docs/auth-service.md) for a plain-language explanation
of the JWT, refresh, CSRF, PostgreSQL, Redis, and logout flows.

From `backend/`, run it directly with:

```bash
uv run --package trialscribe-auth uvicorn trialscribe_auth.api.app:app --host 0.0.0.0 --port 8001
```

Health is available at `GET /health/live` and `GET /health/ready`.

From the repository root, generate local keys, migrate, and test with:

```bash
./scripts.sh auth keys
./scripts.sh db migrate
./scripts.sh auth test
```

Authentication routes are:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`
- `POST /v1/auth/logout-all`
- `GET /v1/auth/me`

Login returns the access token in JSON and sets `trialscribe_refresh` as an HttpOnly,
SameSite cookie. Refresh and current-session logout require the readable `trialscribe_csrf`
cookie value in `X-CSRF-Token`. Use HTTPS and `AUTH_COOKIE_SECURE=true` outside local
development; never commit `.env` or generated signing/HMAC secrets.
