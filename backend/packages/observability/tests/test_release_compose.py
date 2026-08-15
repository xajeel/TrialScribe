from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE = REPO_ROOT / "docker-compose.yml"
RELEASE = REPO_ROOT / "infra" / "release" / "compose.yml"
LOAD = REPO_ROOT / "infra" / "release" / "load.yml"
PROMETHEUS_RELEASE = REPO_ROOT / "infra" / "prometheus" / "prometheus.release.yml"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
WEB_DOCKERFILE = REPO_ROOT / "frontend" / "web" / "Dockerfile"
K6_SCRIPT = REPO_ROOT / "infra" / "k6" / "release.js"

RELEASE_SERVICES = (
    "migrate:",
    "gateway:",
    "auth:",
    "user:",
    "ai:",
    "worker:",
    "jobs:",
    "web:",
)
RELEASE_TARGETS = (
    "gateway:8000",
    "auth:8001",
    "user:8002",
    "ai:8003",
    "worker:8004",
    "jobs:8006",
)


def test_compose_does_not_include_removed_demo_services() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "streamlit-ui:" not in text
    assert "ai-engine:" not in text
    assert "legacy" not in text


def test_release_overlay_has_migrate_gate_and_loopback_binds() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    for service in RELEASE_SERVICES:
        assert service in text
    assert "service_completed_successfully" in text
    assert "127.0.0.1:${GATEWAY_PORT:-8000}:8000" in text
    assert "127.0.0.1:${RELEASE_WEB_PORT:-8080}:80" in text
    assert "WORKER_CHAT_PROVIDER: fake" in text
    assert "WORKER_EMBEDDING_PROVIDER: fake" in text
    cors_lines = [line for line in text.splitlines() if "CORS" in line]
    assert cors_lines
    assert all("*" not in line for line in cors_lines)


def test_prometheus_release_scrapes_docker_dns_not_the_host() -> None:
    text = PROMETHEUS_RELEASE.read_text(encoding="utf-8")
    for target in RELEASE_TARGETS:
        assert target in text
    assert "host.docker.internal" not in text


def test_release_images_pin_uv_nginx_and_node() -> None:
    backend = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    web = WEB_DOCKERFILE.read_text(encoding="utf-8")
    assert "uv:0.10.7" in backend
    assert "python:3.12.3-slim-bookworm" in backend
    assert "nginx:1.30.4-alpine" in web
    assert "node:24.18.0-alpine" in web


def test_k6_script_and_image_pin() -> None:
    script = K6_SCRIPT.read_text(encoding="utf-8")
    assert "http_req_failed" in script
    assert "p(95)<" in script
    assert "K6_P95_MS" in script
    compose = RELEASE.read_text(encoding="utf-8")
    check = (REPO_ROOT / "scripts" / "check_release.py").read_text(encoding="utf-8")
    assert "grafana/k6:2.2.0" in check
    assert "K6_VUS" in script
    assert compose  # overlay stays present beside the load file


def test_load_overlay_raises_gateway_rate_limits() -> None:
    text = LOAD.read_text(encoding="utf-8")
    assert "GATEWAY_RATE_LIMIT_REQUESTS" in text
    assert "100000" in text
    assert "GATEWAY_RATE_LIMIT_AUTH_REQUESTS" in text
    assert "10000" in text
