from trialscribe_ai.api.app import app
from trialscribe_ai.agents.graph import graph_builder
from trialscribe_ai.retrieval.trial_processor import TrialDataProcessor


def test_api_app_imports():
    assert app.title == "TrialScribe API"


def test_graph_builder_compiles():
    graph = graph_builder()
    assert graph is not None


def test_trial_data_processor_round_trip():
    processor = TrialDataProcessor()
    sample = {
        "titleLong": "Sample Trial",
        "phase": {"name": "Phase 2"},
    }
    result = processor.process_json(sample)
    assert result["basic_info"]["title"] == "Sample Trial"
    assert result["basic_info"]["phase"] == "Phase 2"
