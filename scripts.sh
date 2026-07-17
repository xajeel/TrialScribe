#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Usage: ./scripts.sh <command>

Commands:
  install  Install frozen backend and React dependencies
  env      Create .env from .env_example when it does not exist
  run      Run one service: gateway, auth, user, ai, worker, or web
  lint     Run Ruff checks and the React TypeScript check
  test     Run every backend service test and the React test suite
  smoke    Start and health-check every platform boundary
  infra    Manage local infrastructure: up, check, down, or test
  db       Manage PostgreSQL schema: migrate, current, or test
  help     Show this help

Compatibility aliases:
  sync     Install backend workspace dependencies
  api      Run the ai-engine service (same as: run ai)
  ui       Run the interim Streamlit UI
  up       Build and start the existing Docker Compose stack
EOF
}

ensure_env() {
  local env_file="$repo_root/.env"
  local example_file="$repo_root/.env_example"
  local key
  local template_line
  local -a infrastructure_keys=(
    POSTGRES_USER
    POSTGRES_PASSWORD
    POSTGRES_DB
    POSTGRES_PORT
    DATABASE_URL
    REDIS_PASSWORD
    REDIS_PORT
    KAFKA_PORT
  )

  if [[ ! -e "$env_file" ]]; then
    cp "$example_file" "$env_file"
    echo "Created .env from .env_example."
    return
  fi

  for key in "${infrastructure_keys[@]}"; do
    if grep -q "^${key}=" "$env_file"; then
      continue
    fi
    template_line="$(grep -m 1 "^${key}=" "$example_file")"
    if [[ -z "$template_line" ]]; then
      echo "Missing ${key} in both .env and .env_example." >&2
      return 1
    fi
    printf '%s\n' "$template_line" >> "$env_file"
  done
}

run_database() {
  local action="${1:-}"
  local -a alembic_command=(
    uv run
    --frozen
    --env-file "$repo_root/.env"
    --package trialscribe-database
    alembic
    -c packages/database/alembic.ini
  )
  local -a test_compose=(
    docker compose
    --env-file .env
    -p trialscribe-db-test
    -f docker-compose.yml
    -f docker-compose.test.yml
    -f docker-compose.database-test.yml
    --profile infrastructure
  )

  ensure_env
  case "$action" in
    migrate)
      (cd "$repo_root/backend" && "${alembic_command[@]}" upgrade head)
      ;;
    current)
      (cd "$repo_root/backend" && "${alembic_command[@]}" current --check-heads)
      ;;
    test)
      (
        cd "$repo_root"
        cleanup_database_test() {
          "${test_compose[@]}" down --volumes --remove-orphans || true
        }
        trap cleanup_database_test EXIT
        cleanup_database_test
        "${test_compose[@]}" up -d --wait --wait-timeout 120 postgres
        python3 "$repo_root/scripts/check_database.py" \
          --project-name trialscribe-db-test \
          --compose-file docker-compose.yml \
          --compose-file docker-compose.test.yml \
          --compose-file docker-compose.database-test.yml
      )
      ;;
    *)
      echo "Unknown database action: ${action:-<missing>}" >&2
      echo "Choose one of: migrate, current, test" >&2
      return 1
      ;;
  esac
}

run_infrastructure() {
  local action="${1:-}"
  local -a dev_compose=(
    docker compose
    --env-file .env
    -p trialscribe-dev
    --profile infrastructure
  )
  local -a test_compose=(
    docker compose
    --env-file .env
    -p trialscribe-test
    -f docker-compose.yml
    -f docker-compose.test.yml
    --profile infrastructure
  )

  case "$action" in
    up)
      ensure_env
      (
        cd "$repo_root"
        "${dev_compose[@]}" up -d --wait --wait-timeout 120 postgres redis kafka
      )
      ;;
    check)
      ensure_env
      python3 "$repo_root/scripts/check_infrastructure.py" \
        --project-name trialscribe-dev \
        --compose-file docker-compose.yml
      ;;
    down)
      ensure_env
      (cd "$repo_root" && "${dev_compose[@]}" down)
      ;;
    test)
      ensure_env
      (
        cd "$repo_root"
        cleanup_test_infrastructure() {
          "${test_compose[@]}" down --volumes --remove-orphans || true
        }
        trap cleanup_test_infrastructure EXIT
        "${test_compose[@]}" up -d --wait --wait-timeout 120 postgres redis kafka
        python3 "$repo_root/scripts/check_infrastructure.py" \
          --project-name trialscribe-test \
          --compose-file docker-compose.yml \
          --compose-file docker-compose.test.yml \
          --verify-restart-persistence
      )
      ;;
    *)
      echo "Unknown infrastructure action: ${action:-<missing>}" >&2
      echo "Choose one of: up, check, down, test" >&2
      return 1
      ;;
  esac
}

run_service() {
  case "${1:-}" in
    gateway)
      (cd "$repo_root/backend" && uv run --package trialscribe-gateway uvicorn trialscribe_gateway.api.app:app --host 0.0.0.0 --port "${GATEWAY_PORT:-8000}")
      ;;
    auth)
      (cd "$repo_root/backend" && uv run --package trialscribe-auth uvicorn trialscribe_auth.api.app:app --host 0.0.0.0 --port "${AUTH_PORT:-8001}")
      ;;
    user)
      (cd "$repo_root/backend" && uv run --package trialscribe-user uvicorn trialscribe_user.api.app:app --host 0.0.0.0 --port "${USER_PORT:-8002}")
      ;;
    ai)
      (cd "$repo_root/backend" && uv run --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --host 0.0.0.0 --port "${AI_PORT:-8003}")
      ;;
    worker)
      (cd "$repo_root/backend" && uv run --package trialscribe-worker uvicorn trialscribe_worker.api.app:app --host 0.0.0.0 --port "${WORKER_PORT:-8004}")
      ;;
    web)
      (cd "$repo_root/frontend/web" && npm run dev -- --host 0.0.0.0 --port "${WEB_PORT:-5173}")
      ;;
    *)
      echo "Unknown service: ${1:-<missing>}" >&2
      echo "Choose one of: gateway, auth, user, ai, worker, web" >&2
      return 1
      ;;
  esac
}

case "${1:-}" in
  install)
    (cd "$repo_root/backend" && uv sync --frozen --all-packages)
    (cd "$repo_root/frontend/web" && npm ci)
    ;;
  env)
    if [[ -e "$repo_root/.env" ]]; then
      echo ".env already exists; leaving it unchanged."
    else
      ensure_env
    fi
    ;;
  run)
    run_service "${2:-}"
    ;;
  lint)
    (
      cd "$repo_root/backend"
      uv run ruff check \
        packages/database \
        services/api-gateway \
        services/auth-service \
        services/user-service \
        services/worker-service \
        services/ai-engine/trialscribe_ai/models/health.py \
        services/ai-engine/tests/test_smoke.py
    )
    (cd "$repo_root/frontend/web" && npm run lint)
    ;;
  test)
    (
      cd "$repo_root/backend"
      uv run pytest \
        packages/database/tests \
        services/api-gateway/tests \
        services/auth-service/tests \
        services/user-service/tests \
        services/ai-engine/tests \
        services/worker-service/tests
    )
    (cd "$repo_root/frontend/web" && npm test)
    ;;
  smoke)
    python3 "$repo_root/scripts/smoke_platform.py"
    ;;
  infra)
    run_infrastructure "${2:-}"
    ;;
  db)
    run_database "${2:-}"
    ;;
  sync)
    (cd "$repo_root/backend" && uv sync --all-packages)
    ;;
  api)
    run_service ai
    ;;
  ui)
    (cd "$repo_root/frontend/streamlit-ui" && uv sync && uv run streamlit run app.py)
    ;;
  up)
    (cd "$repo_root" && docker compose up --build)
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
