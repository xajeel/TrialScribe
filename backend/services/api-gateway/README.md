# API gateway

The API gateway is the public backend entry point. The web application calls the
gateway on port `8000`; the gateway authenticates requests and forwards them to
the independently runnable services. It does not import another service's app.

## Route map

| Public route | Upstream | Forwarded path | Access |
| --- | --- | --- | --- |
| `/v1/auth/*` | auth service | unchanged | register, login, refresh, and logout are anonymous; every other route requires a bearer token |
| `/v1/organizations*` | user service | unchanged | bearer token required |
| `/v1/organization-invitations/*` | user service | unchanged | bearer token required |
| `/v1/ai/*` | AI service | `/v1/ai` removed | bearer token and organization membership required |
| `/v1/jobs/*` | worker service | `/v1/jobs` removed | bearer token and organization membership required |

AI and job requests must include `X-Organization-ID` as a UUID. Before proxying
them, the gateway asks the user service whether the authenticated account belongs
to that organization. Clients cannot supply trusted identity headers: the gateway
removes them and writes its own `X-TrialScribe-Account-ID` and
`X-TrialScribe-Organization-ID` values. `X-Organization-ID` remains the client's
organization-selection header and is never trusted as internal identity.

Every request receives a UUID `X-Request-ID`. A valid caller-provided value is
preserved through membership checks and the final upstream call; an absent or
invalid value is replaced. The response exposes the same ID for tracing.

Request and response bodies are streamed instead of buffered. Upstream response
status, safe headers, and repeated `Set-Cookie` headers are preserved. The gateway
does not retry requests: an unavailable upstream returns `503`, and an upstream
timeout returns `504`. Missing or invalid authentication returns `401`; a missing,
malformed, or non-UUID organization context returns `422`; and a valid organization
for which the user lacks membership returns `403`. Error responses use fixed public
messages and do not expose internal exception details.

## Run locally

Create or update the repository `.env`, start the required infrastructure and
services in separate terminals, then run the gateway:

```bash
./scripts.sh env
./scripts.sh infra up
./scripts.sh run auth
./scripts.sh run user
./scripts.sh run ai
./scripts.sh run worker
./scripts.sh run gateway
```

The helper loads the repository `.env` and listens on `GATEWAY_PORT` (default
`8000`). Configure the four `GATEWAY_*_SERVICE_URL` values when the downstream
services are not using their default local ports. Credentialed browser origins
must be explicitly listed in `GATEWAY_CORS_ORIGINS`.

Process health is available at `GET /health/live`; gateway readiness is available
at `GET /health/ready`. Readiness reports only the gateway lifecycle state and
does not probe downstream services.
