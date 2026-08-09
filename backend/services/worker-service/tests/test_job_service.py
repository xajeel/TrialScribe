import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from trialscribe_events.contracts.job import JobRequested, register_job_events
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.constant import MAX_JOB_PARAMETERS_BYTES
from trialscribe_events.utils.exceptions import EventPublishError

from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.services.jobs import JobService
from trialscribe_worker.utils.enum import (
    TERMINAL_JOB_STATUSES,
    JobErrorCode,
    JobStatus,
)
from trialscribe_worker.utils.exceptions import (
    InvalidJobInputError,
    JobAlreadyFinishedError,
    JobNotFoundError,
    JobQueueUnavailableError,
    UnsupportedJobKindError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000031")
OTHER_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000032")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000033")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000034")
NOW = datetime(2026, 8, 9, 11, 0, 0, tzinfo=UTC)
TTL_SECONDS = 3600


class FakeKeyValueStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get(self, name: str) -> Any:
        return self.values.get(name)

    async def set(self, name: str, value: str, ex: int | None = None) -> Any:
        self.values[name] = value
        return True

    async def delete(self, *names: str) -> Any:
        for name in names:
            self.values.pop(name, None)
        return len(names)


class FakeJobRepository:
    """Mirror the repository's conditional writes, not a database driver.

    Each method applies exactly the status guard its real statement carries, so a
    test can never pass because the double was more permissive than PostgreSQL.
    """

    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}

    async def add(self, job: Job) -> Job:
        job.id = job.id or uuid4()
        job.created_at = NOW
        job.updated_at = NOW
        self.jobs[job.id] = job
        return job

    async def get(self, organization_id: UUID, job_id: UUID) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None or job.organization_id != organization_id:
            return None
        return job

    async def cancel_queued(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> Job | None:
        job = await self.get(organization_id, job_id)
        if job is None or job.status != JobStatus.QUEUED.value:
            return None
        job.status = JobStatus.CANCELLED.value
        job.error_code = JobErrorCode.CANCELLED.value
        job.cancel_requested_at = now
        job.finished_at = now
        return job

    async def request_cancel(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> Job | None:
        job = await self.get(organization_id, job_id)
        if job is None or JobStatus(job.status) in TERMINAL_JOB_STATUSES:
            return None
        job.cancel_requested_at = job.cancel_requested_at or now
        return job


class FakePublisher:
    def __init__(self, fail: bool = False) -> None:
        self.published: list[EventEnvelope] = []
        self.fail = fail

    async def publish(self, envelope: EventEnvelope) -> None:
        if self.fail:
            raise EventPublishError("event could not be published")
        self.published.append(envelope)


def build_service(
    fail_publish: bool = False,
) -> tuple[JobService, FakeJobRepository, FakePublisher, FakeKeyValueStore]:
    repository = FakeJobRepository()
    client = FakeKeyValueStore()
    publisher = FakePublisher(fail=fail_publish)
    service = JobService(
        repository,  # type: ignore[arg-type]
        JobProgressStore(client, TTL_SECONDS),
        publisher,  # type: ignore[arg-type]
        register_job_events(EventRegistry()),
    )
    return service, repository, publisher, client


def request(**overrides: Any) -> JobCreateRequest:
    values: dict[str, Any] = {"kind": "probe", "parameters": {"steps": 2}}
    values.update(overrides)
    return JobCreateRequest(**values)


def stored_job(repository: FakeJobRepository) -> Job:
    return next(iter(repository.jobs.values()))


def test_a_requested_job_is_recorded_queued_and_announced_exactly_once() -> None:
    service, repository, publisher, _ = build_service()

    job = asyncio.run(
        service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW)
    )

    assert job.status is JobStatus.QUEUED
    assert job.attempt == 0
    assert len(publisher.published) == 1
    envelope = publisher.published[0]
    assert envelope.subject == str(job.id)
    assert envelope.correlation_id == job.correlation_id
    assert envelope.partition_key() == str(job.id).encode("utf-8")
    payload = JobRequested.model_validate(envelope.payload)
    assert payload.job_id == job.id
    assert payload.attempt == 1
    assert payload.parameters == {"steps": 2}
    assert stored_job(repository).id == job.id


def test_a_queue_that_cannot_take_the_job_refuses_the_request() -> None:
    service, _, publisher, _ = build_service(fail_publish=True)

    with pytest.raises(JobQueueUnavailableError):
        asyncio.run(service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW))

    assert publisher.published == []


def test_a_kind_this_worker_does_not_serve_is_refused_before_anything_is_written() -> None:
    service, repository, publisher, _ = build_service()

    with pytest.raises(UnsupportedJobKindError):
        asyncio.run(
            service.request_job(
                ORGANIZATION_ID,
                ACCOUNT_ID,
                request(kind="section-generation"),
                NOW,
            )
        )

    assert repository.jobs == {}
    assert publisher.published == []


def test_parameters_larger_than_the_contract_allows_are_refused() -> None:
    service, repository, _, _ = build_service()
    oversize = {"blob": "x" * (MAX_JOB_PARAMETERS_BYTES + 1)}

    with pytest.raises(InvalidJobInputError):
        asyncio.run(
            service.request_job(
                ORGANIZATION_ID,
                ACCOUNT_ID,
                request(parameters=oversize),
                NOW,
            )
        )

    assert repository.jobs == {}


def test_reading_a_job_reports_the_higher_of_its_live_and_durable_progress() -> None:
    service, repository, _, client = build_service()
    job = asyncio.run(service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW))
    stored_job(repository).progress = 40

    without_live = asyncio.run(service.get_job(ORGANIZATION_ID, job.id))
    client.values[f"trialscribe:job:progress:{job.id}"] = "70"
    with_live = asyncio.run(service.get_job(ORGANIZATION_ID, job.id))
    client.values[f"trialscribe:job:progress:{job.id}"] = "5"
    with_stale_live = asyncio.run(service.get_job(ORGANIZATION_ID, job.id))

    assert without_live.progress == 40
    assert with_live.progress == 70
    assert with_stale_live.progress == 40


def test_a_job_belonging_to_another_organization_is_simply_not_found() -> None:
    service, _, _, _ = build_service()
    job = asyncio.run(service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW))

    with pytest.raises(JobNotFoundError):
        asyncio.run(service.get_job(OTHER_ORGANIZATION_ID, job.id))


def test_cancelling_a_waiting_job_finishes_it_without_raising_a_flag() -> None:
    service, _, _, client = build_service()
    job = asyncio.run(service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW))

    response = asyncio.run(service.cancel_job(ORGANIZATION_ID, job.id, NOW))

    assert response.status is JobStatus.CANCELLED
    assert response.error_code is JobErrorCode.CANCELLED
    assert response.finished_at == NOW
    assert client.values == {}


def test_cancelling_a_running_job_raises_the_flag_it_will_check() -> None:
    service, repository, _, client = build_service()
    job = asyncio.run(service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW))
    stored_job(repository).status = JobStatus.RUNNING.value

    response = asyncio.run(service.cancel_job(ORGANIZATION_ID, job.id, NOW))

    assert response.status is JobStatus.RUNNING
    assert response.cancel_requested_at == NOW
    assert client.values[f"trialscribe:job:cancel:{job.id}"] == "1"
    assert stored_job(repository).finished_at is None


def test_cancelling_a_job_that_already_finished_is_refused() -> None:
    service, repository, _, _ = build_service()
    job = asyncio.run(service.request_job(ORGANIZATION_ID, ACCOUNT_ID, request(), NOW))
    stored_job(repository).status = JobStatus.SUCCEEDED.value
    stored_job(repository).finished_at = NOW

    with pytest.raises(JobAlreadyFinishedError):
        asyncio.run(service.cancel_job(ORGANIZATION_ID, job.id, NOW))


def test_cancelling_a_job_that_does_not_exist_is_not_found() -> None:
    service, _, _, _ = build_service()

    with pytest.raises(JobNotFoundError):
        asyncio.run(service.cancel_job(ORGANIZATION_ID, uuid4(), NOW))
