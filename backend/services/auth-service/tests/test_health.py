from fastapi.testclient import TestClient

from trialscribe_auth.api.app import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "auth-service",
        "version": "0.1.0",
    }


def test_readiness() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "auth-service",
        "version": "0.1.0",
    }
