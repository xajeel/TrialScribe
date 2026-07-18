# TrialScribe

**TrialScribe** is an AI-powered clinical research assistant that researches and drafts
clinical trial protocol documents in the **ICH M11 format**. Its LangGraph pipeline gathers
evidence and composes structured, citation-backed protocol sections.

The repository is a service-oriented monorepo. Gateway, authentication, user, AI, worker,
and React boundaries can be run and verified independently before later features add their
domain behavior.

See [docs/architecture.md](docs/architecture.md) for the full system design and roadmap, and
[docs/auth-service.md](docs/auth-service.md) for the authentication and session flow.

## Quickstart

Install `uv`, Node.js 24.18.0, npm 11.16.0, and Docker Compose 2.24.4 or newer,
then run:

```bash
./scripts.sh env
./scripts.sh install
./scripts.sh infra up
./scripts.sh infra check
./scripts.sh db migrate
./scripts.sh auth keys
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
| Start local infrastructure | `./scripts.sh infra up` |
| Check local infrastructure | `./scripts.sh infra check` |
| Stop local infrastructure | `./scripts.sh infra down` |
| Test isolated infrastructure | `./scripts.sh infra test` |
| Migrate PostgreSQL to current | `./scripts.sh db migrate` |
| Check PostgreSQL revision | `./scripts.sh db current` |
| Test isolated database lifecycle | `./scripts.sh db test` |
| Generate local authentication keys | `./scripts.sh auth keys` |
| Test isolated authentication lifecycle | `./scripts.sh auth test` |
| Show command help | `./scripts.sh help` |

The existing `sync`, `api`, `ui`, and `up` commands remain compatibility aliases. `api` now
uses the AI boundary's standard port 8003; `ui` continues to run the interim Streamlit app,
and `up` continues to use the existing Docker Compose stack.

## Local infrastructure

`./scripts.sh infra up` starts PostgreSQL with pgvector on `127.0.0.1:5432`, Redis on
`127.0.0.1:6379`, and Apache Kafka on `127.0.0.1:9092`. The command creates `.env` from
`.env_example` when needed and waits until all three containers are healthy. Update the
local-only placeholder passwords in `.env` when your environment requires different values.

Development data lives in Docker named volumes under the `trialscribe-dev` Compose project.
`infra down` stops containers without deleting those volumes, so ordinary stops and restarts
preserve data. To explicitly remove development containers and data, run:

```bash
docker compose --env-file .env -p trialscribe-dev --profile infrastructure down --volumes
```

`./scripts.sh infra test` uses the separate `trialscribe-test` project without publishing
host ports. It verifies database, vector, Redis, and Kafka operations across a restart, then
always removes its test containers, network, and volumes.

## PostgreSQL schema lifecycle

`./scripts.sh db migrate` applies the ordered Alembic migrations using `DATABASE_URL` from
`.env`; `./scripts.sh db current` verifies that database is at the single current revision.
Neither command prints the connection URL or password.

`./scripts.sh db test` is destructive only to its isolated `trialscribe-db-test` Compose
project. It starts a fresh PostgreSQL volume on a Docker-assigned loopback port, tests empty
and previous-revision upgrades, transaction rollback, organization scope, pgvector, and
restart persistence, then always removes its containers, network, and volume.

## Local authentication

Run `./scripts.sh auth keys` once to fill empty Ed25519 signing-key and HMAC-secret
placeholders in `.env` without printing or replacing existing values. After infrastructure is
healthy and `./scripts.sh db migrate` has run, start the service with `./scripts.sh run auth`.

Individuals can register at `POST /v1/auth/register` and log in at `POST /v1/auth/login`.
The access token is returned in JSON; the refresh token is restricted to an HttpOnly,
SameSite cookie. Browser calls to refresh or current-session logout must copy the readable
`trialscribe_csrf` cookie into the `X-CSRF-Token` header. Organization invitation and
membership behavior belongs to the next organization-RBAC feature and will reuse these global
accounts.

`./scripts.sh auth test` is destructive only to the isolated `trialscribe-auth-test` project.
It migrates a fresh database, proves registration, login, token rotation/replay rejection,
logout scopes, throttling, and persistence across PostgreSQL/Redis restarts, then removes all
test containers and volumes. Production deployments require HTTPS, `AUTH_COOKIE_SECURE=true`,
and externally managed non-placeholder keys and secrets.

## Repository layout

- `backend/` — uv workspace containing gateway, auth, user, AI, and worker packages.
- `backend/packages/database/` — shared PostgreSQL runtime and ordered migrations.
- `frontend/web/` — supported React application shell.
- `frontend/streamlit-ui/` — interim standalone Streamlit UI.
- `infra/` — local Docker Compose initialization assets.
