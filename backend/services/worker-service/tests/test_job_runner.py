import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from trialscribe_events.config import EventBusSettings
from trialscribe_events.contracts.job import JobRequested, register_job_events
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.job import Job
from trialscribe_worker.pipelines.probe import probe_pipeline
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.services.job_runner import JobContext, JobRunner
from trialscribe_worker.utils.constant import (
    PROBE_FAIL_ATTEMPTS_PARAMETER,
    PROBE_STEP_SECONDS_PARAMETER,
    PROBE_STEPS_PARAMETER,
)
from trialscribe_worker.utils.enum import JobErrorCode, JobKind, JobStatus
from trialscribe_worker.utils.exceptions import (
    JobAttemptFailedError,
    JobCancelledError,
    JobNotFoundError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000051")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000052")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000053")
MAX_ATTEMPTS = 3


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


class FakeJobStore:
    """Hold jobs and apply the same status guards the real statements carry."""

    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}
        self.finishes: list[tuple[UUID, str]] = []

    def seed(self, **overrides: Any) -> Job:
        job = Job(
            id=overrides.pop("id", uuid4()),
            organization_id=ORGANIZATION_ID,
            conversation_id=None,
            requested_by_account_id=ACCOUNT_ID,
            correlation_id=CORRELATION_ID,
            kind=overrides.pop("kind", JobKind.PROBE.value),
            status=overrides.pop("status", JobStatus.QUEUED.value),
            attempt=overrides.pop("attempt", 0),
            progress=overrides.pop("progress", 0),
            parameters=overrides.pop("parameters", {}),
        )
        for name, value in overrides.items():
            setattr(job, name, value)
        self.jobs[job.id] = job
        return job


class FakeJobRepository:
    def __init__(self, store: FakeJobStore) -> None:
        self._store = store

    async def claim(self, job_id: UUID, now: datetime) -> Job | None:
        job = self._store.jobs.get(job_id)
        if job is None or JobStatus(job.status).is_terminal():
            return None
        job.status = JobStatus.RUNNING.value
        job.attempt += 1
        job.started_at = job.started_at or now
        return job

    async def exists(self, job_id: UUID) -> bool:
        return job_id in self._store.jobs

    async def mark_retrying(self, job_id: UUID, now: datetime) -> bool:
        job = self._store.jobs.get(job_id)
        if job is None or job.status != JobStatus.RUNNING.value:
            return False
        job.status = JobStatus.RETRYING.value
        return True

    async def finish(
        self,
        job_id: UUID,
        status: Any,
        now: datetime,
        *,
        error_code: Any = None,
        progress: int | None = None,
    ) -> bool:
        job = self._store.jobs.get(job_id)
        if job is None or job.status != JobStatus.RUNNING.value:
            return False
        job.status = status.value
        job.error_code = None if error_code is None else error_code.value
        job.finished_at = now
        if progress is not None:
            job.progress = max(job.progress, progress)
        self._store.finishes.append((job_id, status.value))
        return True

    async def record_progress(self, job_id: UUID, progress: int) -> datetime | None:
        job = self._store.jobs.get(job_id)
        if job is None:
            return None
        job.progress = max(job.progress, progress)
        return job.cancel_requested_at


class FakeRuntime:
    def __init__(self, store: FakeJobStore) -> None:
        self._store = store
        self.transactions = 0

    @asynccontextmanager
    async def transaction(self) -> Any:
        self.transactions += 1
        yield self._store


def build_runner(
    store: FakeJobStore,
    pipelines: dict[JobKind, Any] | None = None,
    persist_step: int = 10,
) -> tuple[JobRunner, FakeKeyValueStore]:
    client = FakeKeyValueStore()
    runner = JobRunner(
        FakeRuntime(store),  # type: ignore[arg-type]
        JobProgressStore(client, 3600),
        WorkerSettings(progress_persist_step=persist_step),
        EventBusSettings(
            bootstrap_servers="localhost:9092",
            max_delivery_attempts=MAX_ATTEMPTS,
        ),
        pipelines if pipelines is not None else {JobKind.PROBE: probe_pipeline},
    )
    return runner, client


@pytest.fixture(autouse=True)
def use_fake_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "trialscribe_worker.services.job_runner.JobRepository",
        FakeJobRepository,
    )


def envelope_for(job: Job) -> EventEnvelope:
    return register_job_events(EventRegistry()).build(
        event_type="job.generation.requested",
        version=1,
        organization_id=ORGANIZATION_ID,
        subject=str(job.id),
        correlation_id=CORRELATION_ID,
        producer="worker-service",
        occurred_at=datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC),
        payload=JobRequested(
            job_id=job.id,
            kind=job.kind,
            organization_id=ORGANIZATION_ID,
            requested_by_account_id=ACCOUNT_ID,
            parameters=job.parameters,
        ),
    )


def run(runner: JobRunner, job: Job, store: FakeJobStore) -> None:
    """Handle one record, passing the store as the session that claims it.

    In production that session is the transaction the event backbone opened to
    record the event as handled, which is exactly why the terminal write goes
    into it: the outcome and the receipt commit together or not at all.
    """

    envelope = envelope_for(job)
    payload = JobRequested.model_validate(envelope.payload)
    asyncio.run(runner.handle(envelope, payload, store))  # type: ignore[arg-type]


def test_a_probe_job_runs_to_completion_and_is_recorded_succeeded() -> None:
    store = FakeJobStore()
    job = store.seed(
        parameters={PROBE_STEPS_PARAMETER: 4, PROBE_STEP_SECONDS_PARAMETER: 0}
    )
    runner, client = build_runner(store)

    run(runner, job, store)

    assert job.status == JobStatus.SUCCEEDED.value
    assert job.progress == 100
    assert job.attempt == 1
    assert job.error_code is None
    assert store.finishes == [(job.id, "succeeded")]
    assert client.values == {}


def test_reported_progress_never_falls_during_a_run() -> None:
    store = FakeJobStore()
    seen: list[int] = []

    async def watching_pipeline(context: JobContext) -> None:
        for percent in (10, 40, 40, 90):
            await context.report(percent)
            seen.append(percent)

    job = store.seed()
    runner, _ = build_runner(store, {JobKind.PROBE: watching_pipeline}, persist_step=1)

    run(runner, job, store)

    assert seen == sorted(seen)
    assert job.progress == 100


def test_a_kind_with_no_pipeline_fails_the_job_without_running_anything() -> None:
    store = FakeJobStore()
    job = store.seed(kind="section-generation")
    runner, _ = build_runner(store)

    run(runner, job, store)

    assert job.status == JobStatus.FAILED.value
    assert job.error_code == JobErrorCode.UNSUPPORTED_KIND.value


def test_a_request_whose_ticket_has_not_landed_yet_is_retried() -> None:
    store = FakeJobStore()
    job = store.seed()
    del store.jobs[job.id]
    runner, _ = build_runner(store)

    with pytest.raises(JobNotFoundError):
        run(runner, job, store)


def test_a_job_that_already_finished_is_left_exactly_as_it_was() -> None:
    store = FakeJobStore()
    job = store.seed(
        status=JobStatus.CANCELLED.value,
        error_code=JobErrorCode.CANCELLED.value,
        attempt=1,
    )
    runner, _ = build_runner(store)

    run(runner, job, store)

    assert job.status == JobStatus.CANCELLED.value
    assert job.attempt == 1
    assert store.finishes == []


def test_a_failure_with_attempts_left_parks_the_job_and_asks_for_redelivery() -> None:
    store = FakeJobStore()
    job = store.seed(parameters={PROBE_FAIL_ATTEMPTS_PARAMETER: MAX_ATTEMPTS})
    runner, _ = build_runner(store)

    with pytest.raises(JobAttemptFailedError):
        run(runner, job, store)

    assert job.status == JobStatus.RETRYING.value
    assert job.attempt == 1
    assert store.finishes == []


def test_the_final_failed_attempt_is_written_down_rather_than_dead_lettered() -> None:
    store = FakeJobStore()
    job = store.seed(
        parameters={PROBE_FAIL_ATTEMPTS_PARAMETER: MAX_ATTEMPTS},
        attempt=MAX_ATTEMPTS - 1,
    )
    runner, _ = build_runner(store)

    run(runner, job, store)

    assert job.status == JobStatus.FAILED.value
    assert job.error_code == JobErrorCode.HANDLER_FAILED.value
    assert store.finishes == [(job.id, "failed")]


def test_a_retried_job_that_stops_failing_succeeds() -> None:
    store = FakeJobStore()
    job = store.seed(
        parameters={
            PROBE_FAIL_ATTEMPTS_PARAMETER: 1,
            PROBE_STEPS_PARAMETER: 2,
            PROBE_STEP_SECONDS_PARAMETER: 0,
        }
    )
    runner, _ = build_runner(store)

    with pytest.raises(JobAttemptFailedError):
        run(runner, job, store)
    run(runner, job, store)

    assert job.status == JobStatus.SUCCEEDED.value
    assert job.attempt == 2


def test_a_stop_flag_raised_in_redis_ends_the_job_cancelled() -> None:
    store = FakeJobStore()
    job = store.seed(
        parameters={PROBE_STEPS_PARAMETER: 20, PROBE_STEP_SECONDS_PARAMETER: 0}
    )
    runner, client = build_runner(store)
    client.values[f"trialscribe:job:cancel:{job.id}"] = "1"

    run(runner, job, store)

    assert job.status == JobStatus.CANCELLED.value
    assert job.error_code == JobErrorCode.CANCELLED.value
    assert job.progress == 0


def test_a_stop_recorded_only_in_the_database_still_ends_the_job() -> None:
    store = FakeJobStore()
    job = store.seed(
        parameters={PROBE_STEPS_PARAMETER: 10, PROBE_STEP_SECONDS_PARAMETER: 0},
        cancel_requested_at=datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC),
    )
    runner, _ = build_runner(store, persist_step=1)

    run(runner, job, store)

    assert job.status == JobStatus.CANCELLED.value
    assert 0 < job.progress < 100


def test_a_cancelled_pipeline_stops_before_doing_the_rest_of_its_work() -> None:
    store = FakeJobStore()
    performed: list[int] = []

    async def counting_pipeline(context: JobContext) -> None:
        for step in range(1, 6):
            await context.check_cancelled()
            performed.append(step)
            await context.report(step * 20)

    job = store.seed(cancel_requested_at=datetime(2026, 8, 9, 13, 0, tzinfo=UTC))
    runner, _ = build_runner(
        store,
        {JobKind.PROBE: counting_pipeline},
        persist_step=1,
    )

    run(runner, job, store)

    assert performed == [1]
    assert job.status == JobStatus.CANCELLED.value


def test_the_pipeline_contract_raises_the_cancellation_the_runner_expects() -> None:
    async def stopping_pipeline(context: JobContext) -> None:
        raise JobCancelledError

    store = FakeJobStore()
    job = store.seed()
    runner, _ = build_runner(store, {JobKind.PROBE: stopping_pipeline})

    run(runner, job, store)

    assert job.status == JobStatus.CANCELLED.value
