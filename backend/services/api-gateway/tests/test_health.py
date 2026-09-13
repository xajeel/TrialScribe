from fastapi.testclient import TestClient

from trialscribe_gateway.api.app import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "api-gateway",
        "version": "0.1.0",
    }


def test_readiness() -> None:
    app.state.gateway_ready = True
    try:
        response = client.get("/health/ready")
    finally:
        app.state.gateway_ready = False

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "api-gateway",
        "version": "0.1.0",
    }


def test_readiness_is_unavailable_before_lifespan() -> None:
    app.state.gateway_ready = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}
