from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import trialscribe_ai.api.app as app_module
from trialscribe_ai.api.app import app
from trialscribe_ai.api.sessions import session_manager
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


def test_missing_session_uses_safe_custom_error() -> None:
    response = client.post(
        "/sessions/missing/upload-json",
        files={"file": ("trial.json", b"{}", "application/json")},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}


def test_processing_exception_text_is_not_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "postgresql://user:secret@internal-host/database"

    class FailingDatabase:
        def add_json_data(self, _data: object) -> None:
            raise RuntimeError(secret)

    session_manager.sessions["failing"] = {
        "created_at": datetime.now(),
        "database": FailingDatabase(),
        "agent": None,
        "summary": None,
        "documents": [],
        "reports": {},
    }
    monkeypatch.setattr(app_module.trial_processor, "process_json", lambda _data: {})
    try:
        response = client.post(
            "/sessions/failing/upload-json",
            files={"file": ("trial.json", b"{}", "application/json")},
        )
    finally:
        session_manager.sessions.pop("failing", None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Trial data processing failed"}
    assert secret not in response.text
