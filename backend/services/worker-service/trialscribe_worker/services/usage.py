"""Assemble a conversation usage snapshot from stored integer micros."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.provider_calls import ProviderCallListRecord
from trialscribe_worker.utils.constant import (
    GENERATE_SECTIONS_PARAMETER,
    USAGE_JOB_LIST_LIMIT,
    USAGE_PRICING_BASIS,
)
from trialscribe_worker.utils.enum import JobStatus, ProviderOperation, ProviderOutcome

_IN_FLIGHT = frozenset(
    {
        JobStatus.QUEUED.value,
        JobStatus.RUNNING.value,
        JobStatus.RETRYING.value,
    }
)
_STAGE_LABELS = {
    ProviderOperation.CHAT.value: "Chat",
    ProviderOperation.EMBED.value: "Embedding",
}
_OUTCOME_LABELS = {
    JobStatus.SUCCEEDED.value: "complete",
    JobStatus.FAILED.value: "failed",
    JobStatus.CANCELLED.value: "cancelled",
}


def build_usage_view(
    *,
    protocol_title: str,
    protocol_id: UUID,
    viewer_account_id: UUID,
    jobs: Sequence[Job],
    calls: Sequence[ProviderCallListRecord],
    summary: tuple[int, int, int, datetime | None],
) -> dict[str, object]:
    """Group stored calls by job. Never copies job parameters into the result."""

    total_cost_micros, input_tokens, output_tokens, updated_at = summary
    calls_by_job: dict[UUID, list[ProviderCallListRecord]] = defaultdict(list)
    for call in calls:
        if call.job_id is None:
            continue
        calls_by_job[call.job_id].append(call)

    unique_jobs: dict[UUID, Job] = {}
    for job in jobs:
        unique_jobs[job.id] = job

    generations: list[dict[str, object]] = []
    for job in unique_jobs.values():
        job_calls = calls_by_job.get(job.id, [])
        if not job_calls and job.status not in _IN_FLIGHT:
            continue
        generations.append(
            _generation(
                job,
                job_calls,
                viewer_account_id,
            )
        )

    generations.sort(key=lambda item: str(item["started_at"]), reverse=True)
    successful_jobs = sum(1 for item in generations if item["outcome"] == "complete")
    failed_or_cancelled = sum(
        1 for item in generations if item["outcome"] in {"failed", "cancelled"}
    )
    generation_count = len(generations)
    return {
        "protocol_title": protocol_title,
        "protocol_id": protocol_id,
        "summary": {
            "total_cost_micros": total_cost_micros,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "successful_jobs": successful_jobs,
            "failed_or_cancelled": failed_or_cancelled,
            "generation_count": generation_count,
            "pricing_basis": USAGE_PRICING_BASIS,
            "updated_at": _iso(updated_at),
        },
        "generations": generations[:USAGE_JOB_LIST_LIMIT],
    }


def _generation(
    job: Job,
    job_calls: Sequence[ProviderCallListRecord],
    viewer_account_id: UUID,
) -> dict[str, object]:
    ordered = sorted(job_calls, key=lambda item: (item.created_at, item.id))
    latest = ordered[-1] if ordered else None
    section_numbers = _section_numbers(job.parameters)
    terminal = JobStatus(job.status).is_terminal()
    started = job.started_at or job.created_at
    return {
        "id": str(job.id),
        "job_id": str(job.id),
        "scope": _scope(section_numbers, job.kind),
        "section_numbers": section_numbers,
        "requester": (
            "You" if job.requested_by_account_id == viewer_account_id else "Unavailable account"
        ),
        "model": "" if latest is None else latest.model,
        "input_tokens": sum(item.input_tokens for item in ordered),
        "output_tokens": sum(item.output_tokens for item in ordered),
        "latency_ms": None if not ordered else sum(item.latency_ms for item in ordered),
        "outcome": _outcome(job.status, ordered),
        "cost_micros": None if not terminal else sum(item.cost_micros for item in ordered),
        "pricing_version": USAGE_PRICING_BASIS if latest is None else latest.pricing_version,
        "started_at": _iso(started),
        "completed_at": _iso(job.finished_at),
        "provider_calls": [_call_item(item) for item in ordered],
    }


def _call_item(call: ProviderCallListRecord) -> dict[str, object]:
    return {
        "id": str(call.id),
        "stage": _STAGE_LABELS.get(call.operation, call.operation),
        "model": call.model,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "latency_ms": call.latency_ms,
        "result": (
            "Complete" if call.outcome == ProviderOutcome.SUCCEEDED.value else call.outcome
        ),
        "cost_micros": call.cost_micros,
    }


def _section_numbers(parameters: object) -> list[str]:
    if not isinstance(parameters, dict):
        return []
    raw = parameters.get(GENERATE_SECTIONS_PARAMETER)
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        return []
    return list(raw)


def _scope(section_numbers: list[str], kind: str) -> str:
    if len(section_numbers) == 1:
        return f"Section {section_numbers[0]}"
    if section_numbers:
        return "Sections " + ", ".join(section_numbers)
    return kind


def _outcome(status: str, job_calls: Sequence[ProviderCallListRecord]) -> str:
    if status == JobStatus.SUCCEEDED.value and any(
        item.outcome != ProviderOutcome.SUCCEEDED.value for item in job_calls
    ):
        return "issue"
    return _OUTCOME_LABELS.get(status, "running")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
