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
  help     Show this help

Compatibility aliases:
  sync     Install backend workspace dependencies
  api      Run the ai-engine service (same as: run ai)
  ui       Run the interim Streamlit UI
  up       Build and start the existing Docker Compose stack
EOF
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
      cp "$repo_root/.env_example" "$repo_root/.env"
      echo "Created .env from .env_example."
    fi
    ;;
  run)
    run_service "${2:-}"
    ;;
  lint)
    (
      cd "$repo_root/backend"
      uv run ruff check \
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
