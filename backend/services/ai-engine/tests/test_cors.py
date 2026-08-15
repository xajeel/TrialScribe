from fastapi.testclient import TestClient

from trialscribe_ai.api.app import app

ATTACKER_ORIGIN = "https://attacker.example.com"
client = TestClient(app)


def test_ai_engine_does_not_advertise_cors_for_foreign_origins() -> None:
    preflight = client.options(
        "/health/live",
        headers={
            "Origin": ATTACKER_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    live = client.get("/health/live", headers={"Origin": ATTACKER_ORIGIN})

    assert "access-control-allow-origin" not in preflight.headers
    assert live.status_code == 200
    assert "access-control-allow-origin" not in live.headers
