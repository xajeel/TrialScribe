from prometheus_client import generate_latest

from trialscribe_observability.metrics import record_job, safe_observe

FORBIDDEN_LABELS = frozenset(
    {"organization_id", "conversation_id", "job_id", "account_id"}
)


def test_safe_observe_swallows_errors() -> None:
    def boom() -> None:
        raise RuntimeError("metrics must never undo work")

    assert safe_observe(boom) is None


def test_record_job_uses_bounded_labels() -> None:
    record_job("probe", "succeeded", 0.01)
    body = generate_latest().decode()
    assert "trialscribe_jobs_total" in body
    assert 'kind="probe"' in body
    assert 'outcome="succeeded"' in body
    for name in FORBIDDEN_LABELS:
        assert f"{name}=" not in body
