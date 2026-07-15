from fastapi.testclient import TestClient

from trialscribe_ai.api.app import app
from trialscribe_ai.agents.graph import graph_builder
from trialscribe_ai.retrieval.trial_processor import TrialDataProcessor

client = TestClient(app)


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
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "ai-engine",
        "version": "2.0.0",
    }


def test_graph_builder_compiles() -> None:
    graph = graph_builder()
    assert graph is not None


def test_trial_data_processor_round_trip() -> None:
    processor = TrialDataProcessor()
    sample = {
        "titleLong": "Sample Trial",
        "phase": {"name": "Phase 2"},
    }
    result = processor.process_json(sample)
    assert result["basic_info"]["title"] == "Sample Trial"
    assert result["basic_info"]["phase"] == "Phase 2"
