import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PROMETHEUS_CONFIG = REPO_ROOT / "infra" / "prometheus" / "prometheus.yml"
DASHBOARDS = REPO_ROOT / "infra" / "grafana" / "dashboards"
FORBIDDEN = ("organization_id", "conversation_id", "job_id")

REQUIRED_TARGETS = (
    "host.docker.internal:8000",
    "host.docker.internal:8001",
    "host.docker.internal:8002",
    "host.docker.internal:8003",
    "host.docker.internal:8004",
    "host.docker.internal:8006",
    "postgres-exporter:9187",
    "redis-exporter:9121",
)


def _exprs(dashboard: dict[str, object]) -> str:
    chunks: list[str] = []
    panels = dashboard.get("panels")
    if not isinstance(panels, list):
        return ""
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        targets = panel.get("targets")
        if not isinstance(targets, list):
            continue
        for target in targets:
            if isinstance(target, dict) and isinstance(target.get("expr"), str):
                chunks.append(target["expr"])
    return "\n".join(chunks)


def test_prometheus_scrapes_every_required_target() -> None:
    text = PROMETHEUS_CONFIG.read_text(encoding="utf-8")
    for target in REQUIRED_TARGETS:
        assert target in text


def test_http_dashboard_shows_api_errors() -> None:
    dashboard = json.loads((DASHBOARDS / "http.json").read_text(encoding="utf-8"))
    exprs = _exprs(dashboard)
    assert "HTTP" in str(dashboard.get("title"))
    assert "trialscribe_http_requests_total" in exprs
    assert 'status=~"5.."' in exprs
    for name in FORBIDDEN:
        assert name not in exprs


def test_jobs_dashboard_shows_failures() -> None:
    dashboard = json.loads((DASHBOARDS / "jobs.json").read_text(encoding="utf-8"))
    exprs = _exprs(dashboard)
    assert "trialscribe_jobs_total" in exprs
    assert "failed" in exprs
    for name in FORBIDDEN:
        assert name not in exprs


def test_events_dashboard_shows_dead_letters() -> None:
    dashboard = json.loads((DASHBOARDS / "events.json").read_text(encoding="utf-8"))
    exprs = _exprs(dashboard)
    assert "trialscribe_events_consumed_total" in exprs
    assert 'result="dead_letter"' in exprs
    for name in FORBIDDEN:
        assert name not in exprs


def test_dependencies_dashboard_shows_infra_and_provider_failures() -> None:
    dashboard = json.loads((DASHBOARDS / "dependencies.json").read_text(encoding="utf-8"))
    exprs = _exprs(dashboard)
    assert "pg_up" in exprs
    assert "redis_up" in exprs
    assert "trialscribe_provider_calls_total" in exprs
    assert "timeout" in exprs or "circuit_open" in exprs or "error" in exprs
    for name in FORBIDDEN:
        assert name not in exprs
