# auth-service

**Status:** planned

Handles authentication and authorization for the TrialScribe platform. Currently the AI
engine has no auth layer — any client with a session ID can use it. This service will own
identity and access control for all backend services.

## Planned responsibility

- Issue and verify JWTs for authenticated requests.
- Role-based access control (RBAC) — e.g. distinguish standard users from org admins.
- Session/token refresh and revocation.

## Planned tech stack

FastAPI, `python-jose` or `pyjwt`, PostgreSQL (shared with `user-service` or its own schema),
Redis for token/session revocation lists.

## Planned API surface

- `POST /auth/login` — exchange credentials for an access + refresh token pair.
- `POST /auth/refresh` — exchange a refresh token for a new access token.
- `POST /auth/logout` — revoke a refresh token.
- `GET /auth/me` — resolve the current identity from a bearer token.
- `POST /auth/verify` — internal endpoint for other services to validate a token.
