# TrialScribe API Gateway

The API gateway is the single public door to the TrialScribe backend. The frontend does not
need to know that authentication, organizations, AI, and jobs are separate services. It sends
every backend request to the gateway, and the gateway forwards it to the correct service.

For a simple mental model, imagine a hospital reception desk:

- The frontend speaks only to reception: the API gateway.
- The access JWT is the person's signed identity badge.
- `X-Organization-ID` tells reception which organization the person wants to work in.
- The user service confirms whether that person currently belongs to the organization.
- `X-Request-ID` is a tracking number attached to the entire request journey.
- Auth, user, AI, and worker services are separate departments behind reception.

## System boundary

```text
Browser or mobile client
          │
          │ HTTP/HTTPS to one public backend address
          ▼
     API gateway
          │
          ├── /v1/auth/*                     ──> Authentication service
          ├── /v1/organizations*             ──> User service
          ├── /v1/organization-invitations/* ──> User service
          ├── /v1/ai/*                       ──> AI service
          └── /v1/jobs/*                     ──> Worker service
```

The gateway is an independent FastAPI application. It communicates with downstream services
over HTTP and never imports their FastAPI applications or business logic. Each service can
still run, test, and deploy independently.

## Route map

| Public gateway route | Destination | Destination path | Requirements |
|---|---|---|---|
| `/v1/auth/*` | Authentication service | Unchanged | Register, login, refresh, and logout are public `POST` operations; other routes require an access JWT |
| `/v1/organizations*` | User service | Unchanged | Valid access JWT |
| `/v1/organization-invitations/*` | User service | Unchanged | Valid access JWT |
| `/v1/ai/*` | AI service | `/v1/ai` removed | Valid access JWT and current organization membership |
| `/v1/jobs/*` | Worker service | `/v1/jobs` removed | Valid access JWT and current organization membership |

For example, `POST /v1/ai/sessions` at the gateway becomes `POST /sessions` at the AI
service. Query parameters and the request body are preserved.

## Protected request flow

Consider an AI request for organization `8f...`:

```text
1. Browser
   POST /v1/ai/sessions
   Authorization: Bearer <access-jwt>
   X-Organization-ID: 8f...
   X-Request-ID: 41...              optional
                  │
                  ▼
2. Gateway validates the JWT
   - Ed25519 signature
   - issuer and audience
   - required identity and time claims
   - access-token type and expiry
                  │
                  ▼
3. Gateway asks the user service
   GET /v1/organizations/8f...
   - same bearer token
   - same X-Request-ID
                  │
                  ▼
4. Membership exists: gateway forwards to the AI service
   POST /sessions
   - same bearer token and X-Request-ID
   - trusted X-TrialScribe-Account-ID
   - trusted X-TrialScribe-Organization-ID
                  │
                  ▼
5. Browser receives the upstream response and the same X-Request-ID
```

The gateway validates the JWT early, but downstream services still receive the bearer token
and perform their own authorization. This gives two security layers: a gateway mistake alone
does not grant access to a protected service.

## Organization safety

The browser supplies `X-Organization-ID` only to select an organization. The gateway does not
trust browser-supplied internal identity headers. It removes any client values for
`X-TrialScribe-Account-ID` and `X-TrialScribe-Organization-ID`, then writes verified values of
its own.

AI and job calls use a live membership check instead of trusting a role stored in the JWT.
Therefore, removing a person from an organization takes effect immediately; the person does
not keep organization access until the 15-minute JWT expires.

## Request IDs

Every request has one UUID `X-Request-ID`:

- A valid UUID supplied by the client is preserved.
- A missing or invalid value is replaced with a generated UUID.
- The same value reaches membership verification and the destination service.
- The gateway returns it in the browser response.

This ID lets logs from multiple services be matched to one user action without placing a
password, token, email, or clinical data in the tracking value.

## Streaming and response forwarding

The gateway streams request and response bodies. It does not first load an entire upload or
AI response into memory. One shared HTTP client also reuses downstream connections instead of
opening a new connection for every request.

It preserves the downstream status, response body, safe headers, content type, and separate
`Set-Cookie` headers. Connection-specific headers are removed because they apply only to one
network hop. Requests are not automatically retried, because repeating registration,
invitation, upload, or other writes could perform the same action twice.

The gateway waits for at most the first upstream body chunk before starting the browser
response. If that first chunk times out, the gateway can still return the fixed `504` response.
After any response bytes have reached the browser, HTTP does not allow changing the status to
`504`; a later timeout therefore closes the upstream response and aborts the incomplete stream
with no HTTPX exception details exposed. Only the first chunk is prefetched, so successful
large responses remain streamed instead of being buffered in gateway memory.

## Safe errors

| Status | Meaning |
|---:|---|
| `401` | The access JWT is missing or invalid |
| `403` | The account is authenticated but does not belong to the selected organization |
| `422` | `X-Organization-ID` is missing, malformed, or not a UUID |
| `503` | A required downstream service is unavailable |
| `504` | A downstream service exceeded its configured timeout |

These responses use fixed public messages. They do not return connection strings, exception
text, stack traces, tokens, or internal service details.

## CORS and browser access

Credentialed browser requests are accepted only from origins explicitly configured in
`GATEWAY_CORS_ORIGINS`. A wildcard origin is rejected. This permits the frontend to use the
authentication service's protected refresh cookies without allowing every website to call
the backend with browser credentials.

## Running locally

Prepare the environment and infrastructure:

```bash
./scripts.sh env
./scripts.sh auth keys
./scripts.sh infra up
./scripts.sh db migrate
```

Run each service in its own terminal:

```bash
./scripts.sh run auth
./scripts.sh run user
./scripts.sh run ai
./scripts.sh run worker
./scripts.sh run gateway
```

The gateway listens on port `8000` by default. Its process health endpoints are
`GET /health/live` and `GET /health/ready`. Run `./scripts.sh smoke` while local
infrastructure is available to start and verify every platform boundary automatically.

## Single-server deployment and future Nginx

All services can initially run as separate containers on one server. Only the frontend and
gateway need public exposure; PostgreSQL, Redis, Kafka, auth, user, AI, and worker remain on
the server's private container network.

```text
Internet
   │
   ▼
Nginx (future TLS and static frontend)
   ├── /            ──> React frontend files
   └── /v1/*        ──> FastAPI API gateway
                           ├── auth container
                           ├── user container
                           ├── AI container
                           └── worker container
```

Nginx would sit in front of both the frontend and the FastAPI gateway. Nginx would normally
terminate HTTPS and serve or route the frontend, while the FastAPI gateway would continue to
own application routing, JWT checks, organization verification, trusted identity headers,
request IDs, and safe downstream errors.
