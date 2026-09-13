# TrialScribe operations

This is the operator handbook for the **release** stack: the Docker Compose deployment that
runs the whole product on one host. It is the v1 production path. The UI is the React app
in `frontend/web`.

## Start

On a clean host with Docker Compose 2.24.4 or newer, `uv`, and Node.js 24.18.0:

```bash
./scripts.sh env
./scripts.sh install
./scripts.sh auth keys
./scripts.sh release up
./scripts.sh release smoke
```

`release up` starts PostgreSQL, Redis, Kafka, Chroma, Prometheus, Grafana, applies the
current database schema, then starts the API gateway, auth, user, AI, worker, jobs reader,
and the React website. Only the gateway, website, Prometheus, and Grafana are published on
loopback (`127.0.0.1`). Everything else stays on the internal Docker network.

Open the website at `http://127.0.0.1:8080` (override with `RELEASE_WEB_PORT`). Port 8000 is
the API gateway only — `GET /` there is JSON 404, not the React app. Interactive API docs
are at `http://127.0.0.1:8000/docs` (Swagger) and `http://127.0.0.1:8000/redoc`. Grafana is
`http://127.0.0.1:3000` (user `admin`, password from `GRAFANA_ADMIN_PASSWORD`).

Stop with `./scripts.sh release down`. Named volumes keep data until you pass `--volumes`.

Never commit `.env`. On HTTPS, set `AUTH_COOKIE_SECURE=true` and replace every
`change-me-local` secret. The release overlay keeps chat and embedding providers on `fake`
so a load run cannot spend vendor quota; point `WORKER_CHAT_PROVIDER` at DeepSeek only after
keys are in place.

## Backup

PostgreSQL is the source of record for accounts, organizations, conversations, jobs, and
evidence text. Redis AOF and Kafka logs are not a clinical backup.

```bash
./scripts.sh release backup
```

That writes a PostgreSQL `pg_dump -Fc` custom-format file to `backups/trialscribe-release.dump` (override the
directory with `RELEASE_BACKUP_DIR`). The command does not print connection URLs or
passwords. Keep dump files off the git tree (`/backups/` is gitignored).

## Restore

Restore stops the application containers, loads the dump, then starts them again:

```bash
./scripts.sh release restore
```

This replaces the live database with the dump. There is no in-place merge. Take a fresh
backup first if you might need the current data.

`./scripts.sh release test` rehearses this: it writes a probe row, dumps, deletes the row,
restores, and checks the row is back.

## Restart

```bash
./scripts.sh release restart
```

Restarts the gateway and checks `/health/live`, `/health/ready`, and the website root.
Compose `restart: unless-stopped` brings a crashed service back on its own.

## Upgrade

Image tags are pinned (Python 3.12.3, uv 0.10.7, nginx 1.30.4-alpine, k6 2.2.0, and the
infrastructure tags in `docker-compose.yml`). To pick up a new build of *this* repository:

```bash
./scripts.sh release down
./scripts.sh release up
```

`up` rebuilds application images and runs the migrate container to the current schema head.
Do not run `alembic downgrade` unless a named revision and a written rollback note exist for
that change.

## Rollback

1. `./scripts.sh release down`
2. Check out the previous known-good git revision (or rebuild the previous image tags).
3. `./scripts.sh release up`
4. If data must go back too, `./scripts.sh release restore` from the dump taken before the
   upgrade.

Prefer restore-from-dump over schema downgrade.

## Load and capacity

```bash
./scripts.sh release load          # 20 virtual users, 30 seconds
./scripts.sh release load --full   # 500 virtual users, 2 minutes
```

Both commands use Grafana k6 (`grafana/k6:2.2.0`) against fake chat and embedding providers.
They temporarily raise the gateway’s per-IP request limits because a single generator address
is standing in for many people. `./scripts.sh release up` keeps the production limits (120
requests and 20 auth requests per minute per IP).

Probe jobs (`kind=probe`) measure queue drain without calling a vendor. The default check
enqueues 10 jobs and expects `succeeded` within 60 seconds. `--full` enqueues 120 jobs
(about one minute of an 8-hour day at 10,000 jobs/day) with a 3-minute budget.

### Mapping

- 10,000 jobs/day spread evenly is about 7 jobs per minute.
- The same 10,000 jobs in an 8-hour workday is about 21 jobs per minute.
- 500 concurrent users means 500 k6 virtual users for 2 minutes on `--full`.

Thresholds: HTTP failed rate under 1%, HTTP p95 under 2 seconds on the scaled
default (20 users / 30 seconds, containers capped at half a CPU), and under
500 ms on `--full` against reference hardware. Every probe job must `succeeded`,
and no out-of-memory kills.

## Reference hardware

Capacity numbers (500 concurrent users, 10,000 jobs per day) may be cited only after
`./scripts.sh release load --full` on a host with **8 vCPU, 32 GiB RAM, and 500 GB SSD**.
A laptop run is the scaled default (`20` users / `30s`) and is not that claim.

## Full check

```bash
./scripts.sh release test
```

Starts a throwaway `trialscribe-release` project, then smoke, backup/restore rehearsal,
gateway restart, probe-job drain, and scaled k6. It always deletes that project’s containers
and volumes when it finishes. Stop a conflicting `./scripts.sh infra up` first if ports 8000,
8080, 9090, or 3000 are already taken.
