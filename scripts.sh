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
  auth     Manage authentication: keys or test
  user     Manage organization RBAC: test
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
    REDIS_URL
    KAFKA_PORT
    GATEWAY_AUTH_SERVICE_URL
    GATEWAY_USER_SERVICE_URL
    GATEWAY_AI_SERVICE_URL
    GATEWAY_WORKER_SERVICE_URL
    GATEWAY_CORS_ORIGINS
    GATEWAY_UPSTREAM_CONNECT_TIMEOUT_SECONDS
    GATEWAY_UPSTREAM_READ_TIMEOUT_SECONDS
    GATEWAY_UPSTREAM_WRITE_TIMEOUT_SECONDS
    GATEWAY_UPSTREAM_POOL_TIMEOUT_SECONDS
    AUTH_JWT_PRIVATE_KEY_B64
    AUTH_JWT_PUBLIC_KEY_B64
    AUTH_JWT_ISSUER
    AUTH_JWT_AUDIENCE
    AUTH_ACCESS_TOKEN_TTL_SECONDS
    AUTH_REFRESH_TOKEN_TTL_SECONDS
    AUTH_COOKIE_SECURE
    AUTH_HMAC_SECRET
    AUTH_LOGIN_ATTEMPT_LIMIT
    AUTH_LOGIN_WINDOW_SECONDS
    USER_INVITATION_TTL_SECONDS
    USER_INVITATION_ACCEPT_URL
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

run_user_service() {
  local action="${1:-}"
  local -a test_compose=(
    docker compose
    --env-file .env
    -p trialscribe-user-test
    -f docker-compose.yml
    -f infra/testing/isolated.yml
    -f infra/testing/organization-rbac.yml
    --profile infrastructure
  )

  ensure_env
  case "$action" in
    test)
      (
        cd "$repo_root"
        cleanup_user_test() {
          "${test_compose[@]}" down --volumes --remove-orphans || true
        }
        trap cleanup_user_test EXIT
        cleanup_user_test
        "${test_compose[@]}" up -d --wait --wait-timeout 120 postgres
        (
          cd "$repo_root/backend"
          uv run --frozen --package trialscribe-user \
            python "$repo_root/scripts/check_organization_rbac.py" \
              --project-name trialscribe-user-test \
              --compose-file docker-compose.yml \
              --compose-file infra/testing/isolated.yml \
              --compose-file infra/testing/organization-rbac.yml
        )
      )
      ;;
    *)
      echo "Unknown user action: ${action:-<missing>}" >&2
      echo "Choose: test" >&2
      return 1
      ;;
  esac
}

replace_empty_env_value() {
  local key="$1"
  local value="$2"
  local env_file="$repo_root/.env"
  local temp_file
  temp_file="$(mktemp)"
  awk -v target="$key" -v replacement="$value" '
    $0 == target "=" { print target "=" replacement; next }
    { print }
  ' "$env_file" > "$temp_file"
  chmod --reference="$env_file" "$temp_file"
  mv "$temp_file" "$env_file"
}

run_authentication() {
  local action="${1:-}"
  local private_key
  local public_key
  local hmac_secret
  local -a test_compose=(
    docker compose
    --env-file .env
    -p trialscribe-auth-test
    -f docker-compose.yml
    -f infra/testing/isolated.yml
    -f infra/testing/authentication.yml
    --profile infrastructure
  )

  ensure_env
  case "$action" in
    keys)
      private_key="$(grep -m 1 '^AUTH_JWT_PRIVATE_KEY_B64=' "$repo_root/.env" | cut -d= -f2-)"
      public_key="$(grep -m 1 '^AUTH_JWT_PUBLIC_KEY_B64=' "$repo_root/.env" | cut -d= -f2-)"
      if [[ -n "$private_key" || -n "$public_key" ]]; then
        if [[ -z "$private_key" || -z "$public_key" ]]; then
          echo "Both authentication signing keys must be empty or populated." >&2
          return 1
        fi
      else
        mapfile -t generated_keys < <(
          cd "$repo_root/backend"
          uv run --frozen --package trialscribe-auth python - <<'PY'
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

private_key = Ed25519PrivateKey.generate()
print(base64.b64encode(private_key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption(),
)).decode())
print(base64.b64encode(private_key.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)).decode())
PY
        )
        replace_empty_env_value AUTH_JWT_PRIVATE_KEY_B64 "${generated_keys[0]}"
        replace_empty_env_value AUTH_JWT_PUBLIC_KEY_B64 "${generated_keys[1]}"
      fi
      hmac_secret="$(grep -m 1 '^AUTH_HMAC_SECRET=' "$repo_root/.env" | cut -d= -f2-)"
      if [[ -z "$hmac_secret" ]]; then
        hmac_secret="$(
          cd "$repo_root/backend"
          uv run --frozen --package trialscribe-auth python -c \
            'import secrets; print(secrets.token_urlsafe(48))'
        )"
        replace_empty_env_value AUTH_HMAC_SECRET "$hmac_secret"
      fi
      echo "Authentication signing and HMAC keys are configured in .env."
      ;;
    test)
      (
        cd "$repo_root"
        cleanup_authentication_test() {
          "${test_compose[@]}" down --volumes --remove-orphans || true
        }
        trap cleanup_authentication_test EXIT
        cleanup_authentication_test
        "${test_compose[@]}" up -d --wait --wait-timeout 120 postgres redis
        (
          cd "$repo_root/backend"
          uv run --frozen --package trialscribe-auth \
            python "$repo_root/scripts/check_authentication.py" \
              --project-name trialscribe-auth-test \
              --compose-file docker-compose.yml \
              --compose-file infra/testing/isolated.yml \
              --compose-file infra/testing/authentication.yml
        )
      )
      ;;
    *)
      echo "Unknown authentication action: ${action:-<missing>}" >&2
      echo "Choose one of: keys, test" >&2
      return 1
      ;;
  esac
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
    -f infra/testing/isolated.yml
    -f infra/testing/database.yml
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
          --compose-file infra/testing/isolated.yml \
          --compose-file infra/testing/database.yml
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
    -f infra/testing/isolated.yml
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
          --compose-file infra/testing/isolated.yml \
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
      ensure_env
      (cd "$repo_root/backend" && uv run --env-file "$repo_root/.env" --package trialscribe-gateway uvicorn trialscribe_gateway.api.app:app --host 0.0.0.0 --port "${GATEWAY_PORT:-8000}")
      ;;
    auth)
      ensure_env
      (cd "$repo_root/backend" && uv run --env-file "$repo_root/.env" --package trialscribe-auth uvicorn trialscribe_auth.api.app:app --host 0.0.0.0 --port "${AUTH_PORT:-8001}")
      ;;
    user)
      ensure_env
      (cd "$repo_root/backend" && uv run --env-file "$repo_root/.env" --package trialscribe-user uvicorn trialscribe_user.api.app:app --host 0.0.0.0 --port "${USER_PORT:-8002}")
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
    ensure_env
    python3 "$repo_root/scripts/smoke_platform.py"
    ;;
  infra)
    run_infrastructure "${2:-}"
    ;;
  db)
    run_database "${2:-}"
    ;;
  auth)
    run_authentication "${2:-}"
    ;;
  user)
    run_user_service "${2:-}"
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
