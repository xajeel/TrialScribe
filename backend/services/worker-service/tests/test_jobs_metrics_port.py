import pytest

from trialscribe_worker.config import WorkerSettings


def test_jobs_metrics_port_defaults_to_8006(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_JOBS_METRICS_PORT", raising=False)
    assert WorkerSettings().jobs_metrics_port == 8006


def test_jobs_metrics_port_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_JOBS_METRICS_PORT", "8010")
    assert WorkerSettings().jobs_metrics_port == 8010
