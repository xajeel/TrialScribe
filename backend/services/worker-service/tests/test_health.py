from contextlib import asynccontextmanager
from typing import Any

from fastapi.testclient import TestClient

from trialscribe_worker.api.app import app

client = TestClient(app)


class ReadySession:
    async def execute(self, _statement: Any) -> None:
        return None


class ReadyDatabase:
    @asynccontextmanager
    async def transaction(self) -> Any:
        yield ReadySession()


class ReadyRedis:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    async def ping(self) -> bool:
        return self.ready


def test_liveness() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "worker-service",
        "version": "0.1.0",
    }


def test_readiness() -> None:
    app.state.database_runtime = ReadyDatabase()
    app.state.redis = ReadyRedis()

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "worker-service",
        "version": "0.1.0",
    }


def test_readiness_failure_is_safe() -> None:
    app.state.database_runtime = ReadyDatabase()
    app.state.redis = ReadyRedis(ready=False)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable"}
