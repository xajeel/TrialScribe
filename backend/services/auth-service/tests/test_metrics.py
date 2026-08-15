from fastapi.testclient import TestClient

from trialscribe_auth.api.app import app
from trialscribe_auth.utils.constant import SERVICE_NAME

client = TestClient(app)


def test_metrics_exposes_http_families() -> None:
    live = client.get("/health/live")
    response = client.get("/metrics")

    assert live.status_code == 200
    assert response.status_code == 200
    body = response.text
    assert "trialscribe_http_requests_total" in body
    assert "trialscribe_http_request_duration_seconds" in body
    assert 'handler="/health/live"' in body
    assert f'service="{SERVICE_NAME}"' in body
    assert "organization_id=" not in body
    assert "conversation_id=" not in body
    assert "job_id=" not in body
