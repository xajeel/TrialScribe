from contextlib import asynccontextmanager
from typing import Any

from fastapi.testclient import TestClient

from trialscribe_ai.api.app import app
from trialscribe_ai.retrieval.trial_processor import TrialDataProcessor

client = TestClient(app)


class HealthyDatabaseRuntime:
    @asynccontextmanager
    async def transaction(self) -> Any:
        class Session:
            async def execute(self, _statement: object) -> None:
                return None

        yield Session()


def test_api_app_imports() -> None:
    assert app.title == "TrialScribe API"


def test_liveness() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-engine",
        "version": "2.0.0",
    }


def test_readiness() -> None:
    previous = getattr(app.state, "database_runtime", None)
    app.state.database_runtime = HealthyDatabaseRuntime()
    try:
        response = client.get("/health/ready")
    finally:
        if previous is None:
            del app.state.database_runtime
        else:
            app.state.database_runtime = previous

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "ai-engine",
        "version": "2.0.0",
    }


def test_trial_data_processor_round_trip() -> None:
    processor = TrialDataProcessor()
    sample = {
        "titleLong": "Sample Trial",
        "phase": {"name": "Phase 2"},
    }
    result = processor.process_json(sample)
    assert result["basic_info"]["title"] == "Sample Trial"
    assert result["basic_info"]["phase"] == "Phase 2"
