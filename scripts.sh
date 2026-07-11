#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: ./scripts.sh <command>

Commands:
  sync    Install backend dependencies (uv sync --all-packages, in backend/)
  api     Run the FastAPI ai-engine service with reload
  ui      Run the Streamlit UI (syncs its own project first)
  lint    Run ruff over the backend workspace
  test    Run the ai-engine smoke tests
  up      Build and start everything via docker compose
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-}" in
  sync)
    (cd "$repo_root/backend" && uv sync --all-packages)
    ;;
  api)
    (cd "$repo_root/backend" && uv run --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --reload)
    ;;
  ui)
    (cd "$repo_root/frontend/streamlit-ui" && uv sync && uv run streamlit run app.py)
    ;;
  lint)
    (cd "$repo_root/backend" && uv run ruff check .)
    ;;
  test)
    (cd "$repo_root/backend" && uv run --package trialscribe-ai pytest services/ai-engine/tests/)
    ;;
  up)
    (cd "$repo_root" && docker compose up --build)
    ;;
  *)
    usage
    exit 1
    ;;
esac
