from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from trialscribe_worker.models.job import Job
from trialscribe_worker.providers.model_catalog import cost_micros
from trialscribe_worker.repositories.provider_calls import ProviderCallListRecord
from trialscribe_worker.services.usage import build_usage_view
from trialscribe_worker.utils.constant import PRICING_VERSION_DEFAULT
from trialscribe_worker.utils.enum import JobKind, JobStatus, ProviderOperation, ProviderOutcome

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000501")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000502")
OTHER_ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000503")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000504")
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def _job(**overrides: Any) -> Job:
    job = Job(
        id=overrides.pop("id", uuid4()),
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        requested_by_account_id=overrides.pop("requested_by_account_id", ACCOUNT_ID),
        correlation_id=uuid4(),
        kind=overrides.pop("kind", JobKind.GENERATE_SECTIONS.value),
        status=overrides.pop("status", JobStatus.SUCCEEDED.value),
        attempt=1,
        progress=100,
        parameters=overrides.pop("parameters", {"section_numbers": ["6"]}),
    )
    job.created_at = NOW
    job.updated_at = NOW
    job.started_at = NOW
    job.finished_at = NOW
    for name, value in overrides.items():
        setattr(job, name, value)
    return job


def _call(
    job_id: UUID,
    *,
    input_tokens: int = 10,
    output_tokens: int = 5,
    cost: int | None = None,
    outcome: str = ProviderOutcome.SUCCEEDED.value,
    operation: str = ProviderOperation.CHAT.value,
    model: str = "fake-chat",
) -> ProviderCallListRecord:
    priced = cost_micros(
        model,
        PRICING_VERSION_DEFAULT,
        input_tokens,
        output_tokens,
    )
    return ProviderCallListRecord(
        id=uuid4(),
        job_id=job_id,
        account_id=ACCOUNT_ID,
        operation=operation,
        model=model,
        pricing_version=PRICING_VERSION_DEFAULT,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_micros=priced if cost is None else cost,
        latency_ms=4,
        outcome=outcome,
        created_at=NOW,
    )


def test_catalog_fake_chat_calls_sum_to_four_micros() -> None:
    first = _job()
    second = _job()
    calls = [_call(first.id), _call(second.id)]
    assert calls[0].cost_micros == 2
    assert calls[1].cost_micros == 2
    view = build_usage_view(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        viewer_account_id=ACCOUNT_ID,
        jobs=[first, second],
        calls=calls,
        summary=(4, 20, 10, NOW),
    )
    summary = view["summary"]
    assert isinstance(summary, dict)
    assert summary["total_cost_micros"] == 4
    generations = view["generations"]
    assert isinstance(generations, list)
    assert [item["cost_micros"] for item in generations] == [2, 2]
    dumped = str(view)
    assert "parameters" not in dumped
    assert "rewrite_instruction" not in dumped
    assert "prompt" not in dumped


def test_running_job_hides_cost_and_other_requester_is_unavailable() -> None:
    job = _job(
        status=JobStatus.RUNNING.value,
        requested_by_account_id=OTHER_ACCOUNT_ID,
        finished_at=None,
        parameters={
            "section_numbers": ["1", "2"],
            "rewrite_instruction": "do not leak this",
        },
    )
    view = build_usage_view(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        viewer_account_id=ACCOUNT_ID,
        jobs=[job],
        calls=[_call(job.id)],
        summary=(2, 10, 5, NOW),
    )
    generations = view["generations"]
    assert isinstance(generations, list)
    row = generations[0]
    assert row["cost_micros"] is None
    assert row["requester"] == "Unavailable account"
    assert row["scope"] == "Sections 1, 2"
    assert row["outcome"] == "running"
    assert "rewrite_instruction" not in str(view)
    assert "do not leak this" not in str(view)


def test_succeeded_job_with_failed_call_is_issue() -> None:
    job = _job(parameters={"section_numbers": ["8"]})
    view = build_usage_view(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        viewer_account_id=ACCOUNT_ID,
        jobs=[job],
        calls=[
            _call(
                job.id,
                outcome=ProviderOutcome.TIMEOUT.value,
                cost=0,
            )
        ],
        summary=(0, 10, 5, NOW),
    )
    generations = view["generations"]
    assert isinstance(generations, list)
    assert generations[0]["outcome"] == "issue"
    assert generations[0]["scope"] == "Section 8"
    assert generations[0]["requester"] == "You"
    calls = generations[0]["provider_calls"]
    assert isinstance(calls, list)
    assert calls[0]["stage"] == "Chat"
    assert calls[0]["result"] == "timeout"
