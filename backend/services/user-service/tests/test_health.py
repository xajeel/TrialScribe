from fastapi.testclient import TestClient

from trialscribe_user.api.app import app

client = TestClient(app)


class FakeSession:
    async def execute(self, _statement: object) -> None:
        return None


class FakeTransaction:
    async def __aenter__(self) -> FakeSession:
        return FakeSession()

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeDatabaseRuntime:
    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


def test_liveness() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "user-service",
        "version": "0.1.0",
    }


def test_readiness() -> None:
    app.state.database_runtime = FakeDatabaseRuntime()
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "user-service",
        "version": "0.1.0",
    }


def test_readiness_hides_database_failures() -> None:
    class FailedTransaction(FakeTransaction):
        async def __aenter__(self) -> FakeSession:
            raise RuntimeError("database secret")

    class FailedDatabaseRuntime(FakeDatabaseRuntime):
        def transaction(self) -> FakeTransaction:
            return FailedTransaction()

    app.state.database_runtime = FailedDatabaseRuntime()
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}
